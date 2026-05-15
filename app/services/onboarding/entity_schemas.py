"""Target schemas for the onboarding agent (MVP entities).

Each schema declares the ordered list of fields that ``import_service`` expects
for a given entity, along with metadata used by the LLM mapper and the local
transformation/validation nodes.

Field order is **the same** as the CSV column order expected by
``app.services.import_service``. Do not reorder.

See ``app/services/import_service.py`` for the canonical CSV formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FieldType = Literal["date", "number", "integer", "text", "enum", "boolean"]


@dataclass(frozen=True)
class FieldSpec:
    """Specification of a single target field."""

    id: str
    label_es: str
    type: FieldType
    required: bool = False
    description: str = ""
    # For enum fields: list of accepted values (lower-case, no accents).
    enum_values: tuple[str, ...] = field(default_factory=tuple)
    # Aliases that strongly hint at this field — used to bias the LLM and to
    # provide a deterministic fallback if the LLM is unavailable.
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EntitySchema:
    """Schema for a supported onboarding entity."""

    id: str
    label_es: str
    description_es: str
    # Ordered fields. CSV output follows this exact order.
    fields: tuple[FieldSpec, ...]

    def required_field_ids(self) -> tuple[str, ...]:
        return tuple(f.id for f in self.fields if f.required)

    def field_ids(self) -> tuple[str, ...]:
        return tuple(f.id for f in self.fields)

    def get(self, field_id: str) -> FieldSpec | None:
        for f in self.fields:
            if f.id == field_id:
                return f
        return None


# ---------------------------------------------------------------------------
# Gastos
#   fecha;concepto;persona;bancal;cantidad[;categoria[;grupo_prorrateo]]
# ---------------------------------------------------------------------------
GASTOS_SCHEMA = EntitySchema(
    id="gastos",
    label_es="Gastos",
    description_es=(
        "Gastos de la explotación (facturas, suministros, mano de obra...). "
        "Cada fila es un apunte con fecha, concepto, persona, bancal opcional, "
        "importe y categoría opcional."
    ),
    fields=(
        FieldSpec(
            id="fecha",
            label_es="Fecha",
            type="date",
            required=True,
            description="Fecha del gasto en formato DD/MM/YYYY",
            aliases=("fecha", "date", "día", "dia"),
        ),
        FieldSpec(
            id="concepto",
            label_es="Concepto",
            type="text",
            required=True,
            description="Descripción del gasto",
            aliases=(
                "concepto",
                "descripcion",
                "descripción",
                "detalle",
                "description",
                "item",
            ),
        ),
        FieldSpec(
            id="persona",
            label_es="Persona",
            type="text",
            required=False,
            description="Persona o proveedor asociado al gasto",
            aliases=(
                "persona",
                "proveedor",
                "supplier",
                "vendor",
                "responsable",
                "quien",
            ),
        ),
        FieldSpec(
            id="bancal",
            label_es="Bancal",
            type="text",
            required=False,
            description=(
                "Nombre de la parcela / bancal. Si está vacío el gasto se "
                "considera general y se prorratea entre todas las parcelas."
            ),
            aliases=(
                "bancal",
                "parcela",
                "finca",
                "plot",
                "lote",
                "sector",
            ),
        ),
        FieldSpec(
            id="cantidad",
            label_es="Cantidad (€)",
            type="number",
            required=True,
            description="Importe en euros, formato europeo (1.250,00)",
            aliases=(
                "cantidad",
                "importe",
                "euros",
                "€",
                "total",
                "amount",
                "precio",
                "coste",
                "gasto",
            ),
        ),
        FieldSpec(
            id="categoria",
            label_es="Categoría",
            type="text",
            required=False,
            description="Categoría libre (ej: Riego, Perros, Mantenimiento)",
            aliases=("categoria", "categoría", "tipo", "category", "rubro"),
        ),
        FieldSpec(
            id="grupo_prorrateo",
            label_es="Grupo de prorrateo",
            type="text",
            required=False,
            description=(
                "Clave para agrupar gastos plurianuales que comparten un "
                "prorrateo. Formato 'P-{id}'. Habitualmente no presente en "
                "ficheros históricos."
            ),
            aliases=("grupo", "prorrateo", "group"),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Ingresos
#   fecha;bancal;kg;categoria;euros_kg
# ---------------------------------------------------------------------------
INGRESOS_SCHEMA = EntitySchema(
    id="ingresos",
    label_es="Ingresos",
    description_es=(
        "Ingresos por venta de trufa. Cada fila es una venta con fecha, "
        "bancal opcional, kilos, calidad (categoría) y precio por kilo."
    ),
    fields=(
        FieldSpec(
            id="fecha",
            label_es="Fecha",
            type="date",
            required=True,
            description="Fecha de venta en formato DD/MM/YYYY",
            aliases=("fecha", "date", "día", "dia"),
        ),
        FieldSpec(
            id="bancal",
            label_es="Bancal",
            type="text",
            required=False,
            description="Nombre de la parcela / bancal de procedencia",
            aliases=("bancal", "parcela", "finca", "plot", "origen"),
        ),
        FieldSpec(
            id="kg",
            label_es="Kg",
            type="number",
            required=True,
            description="Kilogramos vendidos, formato europeo (2,500)",
            aliases=(
                "kg",
                "kilos",
                "kilogramos",
                "peso",
                "cantidad",
                "weight",
            ),
        ),
        FieldSpec(
            id="categoria",
            label_es="Categoría / Calidad",
            type="enum",
            required=False,
            description=(
                "Calidad/categoría de la trufa. Valores: A, B, C, D, "
                "extra, primera, segunda, blanda, agusanada."
            ),
            enum_values=(
                "a",
                "b",
                "c",
                "d",
                "extra",
                "primera",
                "segunda",
                "blanda",
                "agusanada",
            ),
            aliases=("categoria", "categoría", "calidad", "tipo", "quality"),
        ),
        FieldSpec(
            id="euros_kg",
            label_es="€/Kg",
            type="number",
            required=True,
            description="Precio por kilo en euros, formato europeo (450,00)",
            aliases=(
                "euros_kg",
                "€/kg",
                "precio/kg",
                "precio kg",
                "precio",
                "euros por kilo",
                "€ por kilo",
                "price",
                "tarifa",
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Parcelas
#   nombre;fecha_plantacion[;poligono;parcela;ref_catastral;hidrante;sector;
#     n_plantas;superficie_ha;inicio_produccion[;tiene_riego[;config_mapa[;
#     recinto[;caudal_riego[;provincia_cod[;municipio_cod[;
#     especie_huesped_defecto]]]]]]]]
# ---------------------------------------------------------------------------
PARCELAS_SCHEMA = EntitySchema(
    id="parcelas",
    label_es="Parcelas",
    description_es=(
        "Parcelas / bancales de la explotación. Cada fila es una parcela con "
        "su nombre, fecha de plantación, datos catastrales y de riego."
    ),
    fields=(
        FieldSpec(
            id="nombre",
            label_es="Nombre",
            type="text",
            required=True,
            description="Nombre de la parcela",
            aliases=("nombre", "name", "parcela", "bancal", "finca"),
        ),
        FieldSpec(
            id="fecha_plantacion",
            label_es="Fecha de plantación",
            type="date",
            required=True,
            description="Fecha de plantación DD/MM/YYYY",
            aliases=(
                "fecha_plantacion",
                "fecha plantación",
                "plantacion",
                "plantación",
                "planting date",
            ),
        ),
        FieldSpec(
            id="poligono",
            label_es="Polígono",
            type="text",
            required=False,
            aliases=("poligono", "polígono", "polygon"),
        ),
        FieldSpec(
            id="parcela_num",
            label_es="Parcela (nº catastral)",
            type="text",
            required=False,
            aliases=("parcela", "num_parcela", "nº parcela", "plot number"),
        ),
        FieldSpec(
            id="ref_catastral",
            label_es="Referencia catastral",
            type="text",
            required=False,
            aliases=(
                "ref_catastral",
                "referencia catastral",
                "catastro",
                "cadastral",
            ),
        ),
        FieldSpec(
            id="hidrante",
            label_es="Hidrante",
            type="text",
            required=False,
            aliases=("hidrante", "hydrant"),
        ),
        FieldSpec(
            id="sector",
            label_es="Sector",
            type="text",
            required=False,
            aliases=("sector",),
        ),
        FieldSpec(
            id="n_plantas",
            label_es="Nº de plantas",
            type="integer",
            required=False,
            aliases=(
                "n_plantas",
                "plantas",
                "num_plantas",
                "número de plantas",
                "plants",
                "arboles",
                "árboles",
            ),
        ),
        FieldSpec(
            id="superficie_ha",
            label_es="Superficie (ha)",
            type="number",
            required=False,
            aliases=(
                "superficie",
                "superficie_ha",
                "hectareas",
                "hectáreas",
                "ha",
                "area",
                "área",
            ),
        ),
        FieldSpec(
            id="inicio_produccion",
            label_es="Inicio de producción",
            type="date",
            required=False,
            aliases=(
                "inicio_produccion",
                "inicio producción",
                "production start",
                "primera produccion",
            ),
        ),
        FieldSpec(
            id="tiene_riego",
            label_es="¿Tiene riego?",
            type="boolean",
            required=False,
            aliases=("tiene_riego", "riego", "irrigation"),
        ),
        FieldSpec(
            id="config_mapa",
            label_es="Configuración de mapa",
            type="text",
            required=False,
            description="Ej: 'A:1-6; B:1-6'",
            aliases=("config_mapa", "mapa", "layout"),
        ),
        FieldSpec(
            id="recinto",
            label_es="Recinto SIGPAC",
            type="text",
            required=False,
            aliases=("recinto",),
        ),
        FieldSpec(
            id="caudal_riego",
            label_es="Caudal de riego (m³/h)",
            type="number",
            required=False,
            aliases=("caudal", "caudal_riego", "flow"),
        ),
        FieldSpec(
            id="provincia_cod",
            label_es="Código provincia",
            type="text",
            required=False,
            aliases=("provincia", "provincia_cod"),
        ),
        FieldSpec(
            id="municipio_cod",
            label_es="Código municipio",
            type="text",
            required=False,
            aliases=("municipio", "municipio_cod"),
        ),
        FieldSpec(
            id="especie_huesped_defecto",
            label_es="Especie huésped por defecto",
            type="enum",
            required=False,
            enum_values=(
                "encina",
                "roble",
                "quejigo",
                "coscoja",
                "avellano",
                "carpe",
                "otros",
            ),
            aliases=("especie", "huesped", "huésped", "especie_huesped"),
        ),
    ),
)


ENTITY_SCHEMAS: dict[str, EntitySchema] = {
    GASTOS_SCHEMA.id: GASTOS_SCHEMA,
    INGRESOS_SCHEMA.id: INGRESOS_SCHEMA,
    PARCELAS_SCHEMA.id: PARCELAS_SCHEMA,
}


def get_schema(entity_type: str) -> EntitySchema:
    """Return the schema for ``entity_type`` or raise KeyError."""
    return ENTITY_SCHEMAS[entity_type]
