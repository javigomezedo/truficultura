"""Catálogo de vídeos tutoriales auto-hosted.

Los ficheros físicos viven en ``app/static/videos/`` con la convención:

* ``{slug}-720p.mp4`` (siempre presente)
* ``{slug}-1080p.mp4`` (opcional, se usa en pantallas >=768px)
* ``{slug}.jpg`` póster

Un vídeo solo aparece en la UI si su fichero 720p existe en disco; así
podemos referenciarlos desde plantillas sin que se muestren botones rotos
mientras el usuario aún no los ha grabado.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

VIDEOS_DIR = Path(__file__).parent / "static" / "videos"


@dataclass(frozen=True)
class HelpVideo:
    slug: str
    title: str
    duration_s: int
    section: str  # agrupa en /ayuda/videos: "primeros_pasos", "diario", "analisis"

    @property
    def src_720p(self) -> str:
        return f"/static/videos/{self.slug}-720p.mp4"

    @property
    def src_1080p(self) -> str:
        return f"/static/videos/{self.slug}-1080p.mp4"

    @property
    def poster(self) -> str:
        return f"/static/videos/{self.slug}.jpg"


HELP_VIDEOS: dict[str, HelpVideo] = {
    "bienvenida": HelpVideo(
        slug="bienvenida",
        title="Bienvenido a Trufiq",
        duration_s=60,
        section="primeros_pasos",
    ),
    "primera_parcela": HelpVideo(
        slug="primera_parcela",
        title="Crea tu primera parcela",
        duration_s=70,
        section="primeros_pasos",
    ),
    "primer_gasto": HelpVideo(
        slug="primer_gasto",
        title="Apunta un gasto en 30 segundos",
        duration_s=50,
        section="diario",
    ),
    "cosecha_movil": HelpVideo(
        slug="cosecha_movil",
        title="Apunta una cosecha desde el móvil",
        duration_s=45,
        section="diario",
    ),
    "importar_excel": HelpVideo(
        slug="importar_excel",
        title="Importar tu Excel de toda la vida",
        duration_s=90,
        section="primeros_pasos",
    ),
    "rentabilidad": HelpVideo(
        slug="rentabilidad",
        title="Mira si tu finca da dinero",
        duration_s=60,
        section="analisis",
    ),
    "asistente_voz": HelpVideo(
        slug="asistente_voz",
        title="Pregúntale al asistente con tu voz",
        duration_s=40,
        section="diario",
    ),
}


def video_file_exists(slug: str) -> bool:
    """True si el fichero 720p existe en disco."""
    video = HELP_VIDEOS.get(slug)
    if video is None:
        return False
    return (VIDEOS_DIR / f"{slug}-720p.mp4").is_file()


def get_video(slug: str) -> HelpVideo | None:
    """Devuelve el vídeo si está catalogado **y** su fichero existe en disco."""
    video = HELP_VIDEOS.get(slug)
    if video is None or not video_file_exists(slug):
        return None
    return video


def available_videos() -> list[HelpVideo]:
    """Lista los vídeos que tienen fichero físico, en orden de catálogo."""
    return [v for v in HELP_VIDEOS.values() if video_file_exists(v.slug)]


SECTION_LABELS: dict[str, str] = {
    "primeros_pasos": "Primeros pasos",
    "diario": "Día a día",
    "analisis": "Análisis y resultados",
}
