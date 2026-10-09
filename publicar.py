"""Publica en @docencia.ia.ar los posts aprobados de posts.json que ya tocan.

Uso:
  python publicar.py            publica lo que corresponde ahora
  python publicar.py verificar  solo prueba el token y las imágenes, no publica

Necesita las variables IG_TOKEN y REPO (usuario/repo, para armar los links
públicos de las imágenes). Lo corre GitHub Actions; ver .github/workflows.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://graph.instagram.com/v23.0"
ARG = timezone(timedelta(hours=-3))
# Un post atrasado se publica solo dentro de esta ventana. Si se pasa (Actions
# caído, token vencido), queda pendiente para que Manu decida.
VENTANA = timedelta(hours=6)

TOKEN = os.environ["IG_TOKEN"].strip()
REPO = os.environ["REPO"]
RAMA = os.environ.get("RAMA", "main")


def llamar(metodo, ruta, **params):
    params["access_token"] = TOKEN
    datos = urllib.parse.urlencode(params).encode()
    url = f"{API}/{ruta}"
    if metodo == "GET":
        req = urllib.request.Request(f"{url}?{datos.decode()}")
    else:
        req = urllib.request.Request(url, data=datos, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode(errors="replace").replace(TOKEN, "***")
        sys.exit(f"Error de Instagram en {ruta}: {e.code} {cuerpo}")


def link(ruta):
    return f"https://raw.githubusercontent.com/{REPO}/{RAMA}/{ruta}"


def esperar_listo(contenedor):
    for _ in range(30):
        estado = llamar("GET", contenedor, fields="status_code")["status_code"]
        if estado == "FINISHED":
            return
        if estado in ("ERROR", "EXPIRED"):
            sys.exit(f"El contenedor {contenedor} quedó en {estado}")
        time.sleep(5)
    sys.exit(f"El contenedor {contenedor} no terminó de procesarse")


def publicar(post):
    hijos = []
    for img in post["imagenes"]:
        c = llamar("POST", "me/media", image_url=link(img), is_carousel_item="true")
        hijos.append(c["id"])
    for h in hijos:
        esperar_listo(h)
    carrusel = llamar("POST", "me/media", media_type="CAROUSEL",
                      children=",".join(hijos), caption=post["texto"])
    esperar_listo(carrusel["id"])
    return llamar("POST", "me/media_publish", creation_id=carrusel["id"])["id"]


def verificar(posts):
    yo = llamar("GET", "me", fields="username,account_type")
    print(f"Token OK: @{yo['username']} ({yo['account_type']})")
    malas = 0
    for post in posts:
        for img in post["imagenes"]:
            try:
                urllib.request.urlopen(urllib.request.Request(link(img), method="HEAD"), timeout=30)
            except urllib.error.URLError as e:
                print(f"Imagen inaccesible: {img} ({e})")
                malas += 1
    print("Imágenes OK" if not malas else f"{malas} imágenes con problemas")
    pendientes = [p["id"] for p in posts if p.get("aprobado") and not p.get("publicado")]
    print("Pendientes:", ", ".join(pendientes) or "ninguno")
    if malas:
        sys.exit(1)


def main():
    with open("posts.json", encoding="utf-8") as f:
        posts = json.load(f)

    if sys.argv[1:] == ["verificar"]:
        verificar(posts)
        return

    ahora = datetime.now(ARG)
    cambios = False
    for post in posts:
        if not post.get("aprobado") or post.get("publicado"):
            continue
        cuando = datetime.fromisoformat(f"{post['fecha']}T{post['hora']}").replace(tzinfo=ARG)
        if not (cuando <= ahora <= cuando + VENTANA):
            continue
        print(f"Publicando {post['id']} ({len(post['imagenes'])} láminas)")
        post["publicado"] = publicar(post)
        post["publicado_en"] = datetime.now(ARG).isoformat(timespec="minutes")
        print(f"Publicado: {post['publicado']}")
        cambios = True
        # Lo guardo enseguida: si el siguiente falla, este no se repite.
        with open("posts.json", "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
            f.write("\n")
    if not cambios:
        print("Nada para publicar ahora.")


if __name__ == "__main__":
    main()
