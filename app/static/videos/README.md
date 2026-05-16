# Vídeos tutoriales — Trufiq

Esta carpeta aloja los vídeos cortos que se incrustan en la UI (botones
"▶️ Vídeo (1 min)") y en `/ayuda/videos`. El catálogo está en
`app/help_videos.py`; un vídeo solo aparece en la UI cuando su fichero
físico está presente aquí.

## Convención de nombres

Para cada vídeo `slug`:

| Fichero                   | Obligatorio | Uso                                  |
|---------------------------|-------------|--------------------------------------|
| `{slug}-720p.mp4`         | Sí          | Fuente por defecto                   |
| `{slug}-1080p.mp4`        | No          | Fuente para pantallas ≥768 px        |
| `{slug}.jpg`              | Recomendado | Póster (primer frame, 1280×720)      |

Slugs actuales: `bienvenida`, `primera_parcela`, `primer_gasto`,
`cosecha_movil`, `importar_excel`, `rentabilidad`, `asistente_voz`.

## Recomendaciones de codificación

* Códec: H.264 (vídeo) + AAC (audio).
* Bitrate orientativo: 2 Mbps para 720p, 4 Mbps para 1080p.
* Activar `faststart` para que el navegador empiece a reproducir antes
  de descargar el fichero completo.

## Comando ffmpeg recomendado

Partiendo de un máster `bienvenida-master.mp4`:

```sh
# 720p
ffmpeg -i bienvenida-master.mp4 \
  -vf "scale=-2:720" \
  -c:v libx264 -preset slow -crf 22 -b:v 2M -maxrate 2.5M -bufsize 4M \
  -c:a aac -b:a 128k \
  -movflags +faststart \
  bienvenida-720p.mp4

# 1080p
ffmpeg -i bienvenida-master.mp4 \
  -vf "scale=-2:1080" \
  -c:v libx264 -preset slow -crf 22 -b:v 4M -maxrate 5M -bufsize 8M \
  -c:a aac -b:a 160k \
  -movflags +faststart \
  bienvenida-1080p.mp4

# Póster (frame en 00:00:03)
ffmpeg -ss 3 -i bienvenida-master.mp4 -frames:v 1 -q:v 2 bienvenida.jpg
```

## Migración futura

Si el catálogo crece, podemos subir los ficheros a Cloudflare R2 y
cambiar solo las propiedades `src_720p` / `src_1080p` / `poster` en
`app/help_videos.py`. El resto de la UI no requiere cambios.
