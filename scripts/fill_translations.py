"""Populate locale .po files with translations.

Run from project root:
    python scripts/fill_translations.py
"""

from __future__ import annotations

import ast
from pathlib import Path


def po_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def po_unescape(value: str) -> str:
    return ast.literal_eval(value)


def extract_po_string(lines: list[str], prefix: str) -> tuple[str, int] | None:
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            value = po_unescape(line[len(prefix) :])
            next_index = index + 1
            while next_index < len(lines) and lines[next_index].startswith('"'):
                value += po_unescape(lines[next_index])
                next_index += 1
            return value, next_index
    return None


def replace_entries(content: str, translations: dict[str, str]) -> str:
    blocks = content.split("\n\n")
    rewritten: list[str] = []

    for block in blocks:
        lines = block.splitlines()
        if not lines:
            rewritten.append(block)
            continue

        msgid_info = extract_po_string(lines, "msgid ")
        if not msgid_info:
            rewritten.append(block)
            continue

        msgid, _ = msgid_info
        if not msgid or msgid not in translations:
            rewritten.append(block)
            continue

        output: list[str] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if line.startswith("#,") and "fuzzy" in line:
                flags = [flag.strip() for flag in line[2:].split(",") if flag.strip()]
                flags = [flag for flag in flags if flag != "fuzzy"]
                if flags:
                    output.append(f"#, {', '.join(flags)}")
                index += 1
                continue
            if line.startswith("msgstr "):
                output.append(f'msgstr "{po_escape(translations[msgid])}"')
                index += 1
                while index < len(lines) and lines[index].startswith('"'):
                    index += 1
                continue
            output.append(line)
            index += 1

        rewritten.append("\n".join(output))

    return "\n\n".join(rewritten)


def append_missing_entries(content: str, translations: dict[str, str]) -> str:
    existing: set[str] = set()
    for block in content.strip().split("\n\n"):
        lines = block.splitlines()
        msgid_info = extract_po_string(lines, "msgid ")
        if msgid_info and msgid_info[0]:
            existing.add(msgid_info[0])

    missing = [key for key in translations if key not in existing]
    if not missing:
        return content

    extra = [
        f'msgid "{po_escape(key)}"\nmsgstr "{po_escape(translations[key])}"'
        for key in missing
    ]
    return content.rstrip() + "\n\n" + "\n\n".join(extra) + "\n"


def fill_locale(po_path: Path, translations: dict[str, str]) -> None:
    content = po_path.read_text(encoding="utf-8")
    content = replace_entries(content, translations)
    content = append_missing_entries(content, translations)
    po_path.write_text(content, encoding="utf-8")


EN = {
    "Mostrar navegación": "Show navigation",
    "Cambiar idioma": "Change language",
    "Español": "Spanish",
    "Inglés": "English",
    "Francés": "French",
    "Iniciar sesión": "Sign in",
    "Crear cuenta": "Create account",
    "Estilo": "Style",
    "Explotación y rentabilidad": "Farm and profitability",
    "Truficultura con presencia más profesional.": "Truficultura with a more professional presence.",
    "Controla campañas, gastos, ingresos y trazabilidad operativa desde un entorno pensado para trabajo real, no solo para almacenar registros.": "Manage campaigns, expenses, income and operational traceability from an environment designed for real work, not just record keeping.",
    "Rentabilidad por campaña": "Profitability by campaign",
    "Visión clara de ingresos, gastos y márgenes por explotación.": "Clear view of income, expenses and margins by farm.",
    "Importación y exportación coherentes": "Consistent import and export",
    "Procesos CSV consistentes para mover datos con menos fricción.": "Consistent CSV workflows to move data with less friction.",
    "Seguimiento operativo": "Operational tracking",
    "Parcelas, riego y actividad reciente en una sola aplicación.": "Plots, irrigation and recent activity in a single application.",
    "Acceso seguro": "Secure access",
    "Accede a tu panel para revisar campañas, movimientos y estado de la explotación.": "Access your dashboard to review campaigns, transactions and farm status.",
    "Cuenta creada correctamente. Ya puedes iniciar sesión.": "Account created successfully. You can now sign in.",
    "Usuario": "User",
    "Contraseña": "Password",
    "Entrar": "Enter",
    "¿No tienes cuenta?": "Don't have an account?",
    "Crear una nueva": "Create a new one",
    "Cuenta individual": "Individual account",
    "Crea un espacio propio para tu explotación.": "Create a dedicated space for your farm.",
    "Cada usuario mantiene sus parcelas, campañas y movimientos de forma independiente, con una experiencia más ordenada desde el primer acceso.": "Each user keeps their plots, campaigns and transactions separate, with a more organized experience from the first login.",
    "Datos separados por usuario": "User-separated data",
    "Cada explotación conserva su propio contexto de gestión.": "Each farm keeps its own management context.",
    "Estructura preparada para crecer": "Structure ready to grow",
    "Parcelas, gastos, ingresos y riego conectados en la misma vista operativa.": "Plots, expenses, income and irrigation connected in the same operational view.",
    "Alta de usuario": "User registration",
    "Cada usuario tiene sus propios datos de parcelas, gastos e ingresos.": "Each user has their own plot, expense and income data.",
    "Apellidos": "Last name",
    "Nombre de usuario": "Username",
    "Mínimo 8 caracteres.": "Minimum 8 characters.",
    "Confirmar contraseña": "Confirm password",
    "¿Ya tienes cuenta?": "Already have an account?",
    "Inicia sesión": "Sign in",
    "Administración": "Administration",
    "Crear Nuevo Usuario": "Create New User",
    "Alta de cuentas con nombre completo, credenciales y nivel de acceso.": "Create accounts with full name, credentials and access level.",
    "Rol": "Role",
    "Administrador": "Administrator",
    "Crear Usuario": "Create User",
    "Editar Usuario": "Edit User",
    "Actualiza los datos de perfil y el rol de acceso del usuario.": "Update the user's profile data and access role.",
    "Estado:": "Status:",
    "Activo": "Active",
    "Desactivado": "Deactivated",
    "Guardar Cambios": "Save Changes",
    "Gestión de Usuarios": "User Management",
    "Control de usuarios, roles y estado de acceso.": "Control users, roles and access status.",
    "No puedes desactivar tu propia cuenta.": "You cannot deactivate your own account.",
    "Estado": "Status",
    "Creado": "Created",
    "Tú": "You",
    "Desactivar": "Deactivate",
    "Activar": "Activate",
    "No hay usuarios aún.": "There are no users yet.",
    "Volver al listado": "Back to list",
    "Este usuario ha sido desactivado. Por favor, contacta con el administrador si necesitas reactivar tu cuenta.": "This user has been deactivated. Please contact the administrator if you need to reactivate your account.",
    "Usuario o contraseña incorrectos.": "Incorrect username or password.",
    "El email no tiene un formato válido.": "The email format is invalid.",
    "Este email ya está registrado.": "This email is already registered.",
    "Las contraseñas no coinciden.": "Passwords do not match.",
    "La contraseña debe tener al menos 8 caracteres.": "Password must be at least 8 characters long.",
    "La contraseña es demasiado larga (máximo 72 bytes).": "The password is too long (maximum 72 bytes).",
    "El usuario ya existe.": "The user already exists.",
    "Parcela no encontrada": "Plot not found",
    "Mapa configurado correctamente": "Map configured successfully",
    "Trufa registrada correctamente": "Truffle recorded successfully",
    "Planta no encontrada": "Plant not found",
    "Último registro eliminado": "Last record deleted",
    "No hay registro para deshacer": "There is no record to undo",
    "Registro de trufa eliminado": "Truffle record deleted",
    "No se ha encontrado el registro": "Record not found",
    "La parcela no tiene plantas configuradas": "The plot has no configured plants",
    "Pozo registrado correctamente": "Well recorded successfully",
    "Registro no encontrado": "Record not found",
    "Pozo actualizado correctamente": "Well updated successfully",
    "Pozo eliminado correctamente": "Well deleted successfully",
    "Gasto registrado correctamente": "Expense recorded successfully",
    "Gasto no encontrado": "Expense not found",
    "Gasto actualizado correctamente": "Expense updated successfully",
    "Gasto eliminado correctamente": "Expense deleted successfully",
    "Recibo cargado correctamente": "Receipt uploaded successfully",
    "Recibo no encontrado": "Receipt not found",
    "Recibo eliminado correctamente": "Receipt deleted successfully",
    "Ingreso registrado correctamente": "Income recorded successfully",
    "Ingreso no encontrado": "Income not found",
    "Ingreso actualizado correctamente": "Income updated successfully",
    "Ingreso eliminado correctamente": "Income deleted successfully",
    "Riego registrado correctamente": "Irrigation recorded successfully",
    "Riego actualizado correctamente": "Irrigation updated successfully",
    "Riego eliminado correctamente": "Irrigation deleted successfully",
    "Parcela creada correctamente": "Plot created successfully",
    "Parcela actualizada correctamente": "Plot updated successfully",
    "Parcela eliminada correctamente": "Plot deleted successfully",
    "Email": "Email",
    "Exportar datos": "Export data",
    "Exportar datos CSV": "Export CSV data",
    "Descarga tus datos en un formato consistente para backup, revisión externa o reutilización en procesos de importación.": "Download your data in a consistent format for backup, external review or reuse in import processes.",
    "Formato compatible con importación": "Import-compatible format",
    "Exportar parcelas": "Export plots",
    "Descarga todas tus parcelas en formato CSV semicolon-delimited y sin cabecera. Incluye tiene_riego (1/0) y config_mapa para poder reconstruir el mapa en otro entorno.": "Download all your plots in semicolon-delimited CSV format without a header. It includes tiene_riego (1/0) and config_mapa so the map can be rebuilt in another environment.",
    "Exportar gastos": "Export expenses",
    "Descarga los gastos con el mismo orden de columnas admitido por la importación. Si un gasto no está asignado a ningún bancal, la columna bancal se exporta vacía.": "Download expenses using the same column order supported by import. If an expense is not assigned to any plot, the plot column is exported empty.",
    "Exportar ingresos": "Export income",
    "Descarga los ingresos en el mismo formato de importación. El total no se exporta porque se calcula automáticamente a partir de kg y euros/kg.": "Download income in the same import format. The total is not exported because it is calculated automatically from kg and euros/kg.",
    "Exportar riego": "Export irrigation",
    "Descarga los registros de riego en formato reutilizable para la importación. El vínculo interno con gastos no se exporta; solo se incluyen los datos funcionales del registro.": "Download irrigation records in a reusable import format. The internal expense link is not exported; only the functional record data is included.",
    "Exportar pozos": "Export wells",
    "Descarga los registros de pozos en formato CSV. El vínculo interno con gastos no se exporta; solo se incluyen los datos funcionales del registro.": "Download wells records in CSV format. The internal expense link is not exported; only the functional record data is included.",
    "Exportar producción": "Export production",
    "Descarga los registros de producción activos para poder importarlos en otro entorno preservando fecha/hora, parcela, planta, peso y origen.": "Download active production records so they can be imported into another environment while preserving date/time, plot, plant, weight and source.",
    "Eventos de pozos": "Well events",
    "Ver pozos": "View wells",
    "Pozos por planta totales": "Total wells per plant",
    "Pozos estimados": "Estimated wells",
    "Recibo del banco": "Bank receipt",
    "Recibo cargado:": "Uploaded receipt:",
    "Ver recibo": "View receipt",
    "Eliminar recibo": "Delete receipt",
    "No hay recibo adjunto": "No attached receipt",
    "PDF o imagen": "PDF or image",
    "Máximo 5MB. Formatos: PDF, JPEG, PNG, GIF, WebP": "Maximum 5MB. Formats: PDF, JPEG, PNG, GIF, WebP",
    "Tipos permitidos: PDF e imágenes (JPEG, PNG, GIF, WebP). Máximo 5MB.": "Allowed types: PDF and images (JPEG, PNG, GIF, WebP). Maximum 5MB.",
    "Filtrar:": "Filter:",
    "Todas las categorías": "All categories",
    "Todas las personas": "All people",
    "Limpiar filtros": "Clear filters",
    "No hay gastos que coincidan con los filtros seleccionados.": "No expenses match the selected filters.",
    "Archivo CSV delimitado por <code>;</code>, sin cabecera, codificación UTF-8.": "CSV file delimited by <code>;</code>, no header, UTF-8 encoding.",
    "No hay plantas configuradas para esta parcela. Configura el mapa para empezar.": "No plants are configured for this plot. Configure the map to get started.",
    "Arrastra el borde inferior para cambiar filas y el borde derecho para columnas. Haz clic en una celda para marcarla como hueco.": "Drag the bottom edge to change rows and the right edge to change columns. Click a cell to mark it as a gap.",
    "Consejo: ajusta filas y columnas arrastrando el borde inferior y derecho de la cuadrícula.": "Tip: adjust rows and columns by dragging the bottom and right edge of the grid.",
    "Vista completa por campaña y bancal para identificar márgenes y tendencias de rentabilidad.": "Complete view by campaign and plot to identify profitability margins and trends.",
    "Los valores muestran la rentabilidad neta (ingresos − gastos). Pase el ratón sobre cada celda para ver el desglose.": "Values show net profitability (income − expenses). Hover each cell to see the breakdown.",
    "No hay parcelas con sistema de riego activado. Actívalo en la configuración de la parcela.": "There are no plots with irrigation enabled. Enable it in the plot settings.",
    "¿Está seguro de que desea eliminar este registro? Esta acción no se puede deshacer.": "Are you sure you want to delete this record? This action cannot be undone.",
    "Visión general de campañas, rentabilidad y actividad reciente con una presentación más sobria y clara para el trabajo diario.": "Overview of campaigns, profitability and recent activity with a cleaner, more sober presentation for daily work.",
    "Los gastos generales (sin bancal asignado) se distribuyen proporcionalmente según el porcentaje de cada bancal.": "General expenses (without an assigned plot) are distributed proportionally according to each plot's percentage.",
    "Carga parcelas, gastos, ingresos, riego, pozos y producción con una interfaz más clara y profesional. Los archivos se procesan puntualmente y no se almacenan en el servidor.": "Upload plots, expenses, income, irrigation, wells and production with a clearer, more professional interface. Files are processed immediately and are not stored on the server.",
    "Solo son obligatorios nombre y fecha de plantación. El resto de columnas pueden omitirse o dejarse vacías.": "Only the name and planting date are required. The remaining columns can be omitted or left empty.",
    "Esta acción insertará todos los registros del archivo en la base de datos. Asegúrate de que el archivo no contiene duplicados.": "This action will insert all records from the file into the database. Make sure the file does not contain duplicates.",
    "Si el bancal está vacío, el gasto se registra como gasto general (sin bancal asignado).": "If the plot is empty, the expense is recorded as a general expense (without an assigned plot).",
    "El bancal debe existir y tener riego habilitado. Las filas que no cumplan esta condición generarán un aviso y serán omitidas.": "The plot must exist and have irrigation enabled. Rows that do not meet this condition will generate a warning and will be skipped.",
    "El bancal y la planta deben existir previamente. Las filas no válidas se omiten con aviso.": "The plot and the plant must already exist. Invalid rows are skipped with a warning.",
    "Asistente no disponible: configura OPENAI_API_KEY en el servidor.": "Assistant unavailable: configure OPENAI_API_KEY on the server.",
    "Has superado el límite temporal de consultas al asistente. Inténtalo de nuevo en unos minutos.": "You have exceeded the temporary limit for assistant queries. Try again in a few minutes.",
    "La parcela no tiene sistema de riego activado": "The plot does not have irrigation enabled",
    "El gasto debe pertenecer a la misma parcela y tener categoría 'Riego'": "The expense must belong to the same plot and have the 'Riego' category",
    "El gasto debe pertenecer a la misma parcela y tener categoría 'Pozos'": "The expense must belong to the same plot and have the 'Pozos' category",
    "No se puede regenerar el mapa: existen registros de trufas activos.": "The map cannot be regenerated because there are active truffle records.",
    "Tipo de archivo no permitido: {content_type}. Permitidos: PDF e imágenes (JPEG, PNG, GIF, WebP)": "File type not allowed: {content_type}. Allowed: PDF and images (JPEG, PNG, GIF, WebP)",
    "Archivo demasiado grande. Máximo: 5MB, Tamaño actual: {size_mb:.1f}MB": "File too large. Maximum: 5MB, current size: {size_mb:.1f}MB",
    "Línea {line}: se esperaban 5 columnas, se encontraron {count} — omitida": "Line {line}: expected 5 columns, found {count} — skipped",
    "Línea {line}: se esperaban al menos 2 columnas, se encontraron {count} — omitida": "Line {line}: expected at least 2 columns, found {count} — skipped",
    "Línea {line}: se esperaban al menos 3 columnas, se encontraron {count} — omitida": "Line {line}: expected at least 3 columns, found {count} — skipped",
    "Línea {line}: se esperaban al menos 4 columnas, se encontraron {count} — omitida": "Line {line}: expected at least 4 columns, found {count} — skipped",
    "Línea {line}: bancal '{plot}' no encontrado — importado sin bancal": "Line {line}: plot '{plot}' not found — imported without plot",
    "Línea {line}: error al parsear los datos — omitida": "Line {line}: data parse error — skipped",
    "Parcela '{plot}': config_mapa inválida — mapa omitido": "Plot '{plot}': invalid map_config — map skipped",
    "Línea {line}: bancal vacío — omitida (el registro de pozos siempre requiere parcela)": "Line {line}: empty plot — skipped (well records always require a plot)",
    "Línea {line}: bancal '{plot}' no encontrado — omitida": "Line {line}: plot '{plot}' not found — skipped",
    "Línea {line}: bancal vacío — omitida (el riego siempre requiere parcela)": "Line {line}: empty plot — skipped (irrigation always requires a plot)",
    "Línea {line}: bancal '{plot}' no tiene riego habilitado — omitida": "Line {line}: plot '{plot}' does not have irrigation enabled — skipped",
    "Línea {line}: bancal vacío — omitida": "Line {line}: empty plot — skipped",
    "Línea {line}: planta vacía — omitida": "Line {line}: empty plant — skipped",
    "Línea {line}: planta '{plant}' no encontrada en bancal '{plot}' — omitida": "Line {line}: plant '{plant}' not found in plot '{plot}' — skipped",
    "El mapa tiene {actual} plantas pero la parcela declara {expected}. Revisa la configuración del mapa.": "The map has {actual} plants but the plot declares {expected}. Review the map configuration.",
    "¿Eliminar el recibo?": "Delete the receipt?",
}

FR = {
    "Mostrar navegación": "Afficher la navigation",
    "Cambiar idioma": "Changer de langue",
    "Español": "Espagnol",
    "Inglés": "Anglais",
    "Francés": "Français",
    "Iniciar sesión": "Se connecter",
    "Crear cuenta": "Créer un compte",
    "Estilo": "Style",
    "Explotación y rentabilidad": "Exploitation et rentabilité",
    "Truficultura con presencia más profesional.": "Truficultura avec une image plus professionnelle.",
    "Controla campañas, gastos, ingresos y trazabilidad operativa desde un entorno pensado para trabajo real, no solo para almacenar registros.": "Pilotez campagnes, dépenses, revenus et traçabilité opérationnelle depuis un environnement conçu pour un usage réel, pas seulement pour stocker des enregistrements.",
    "Rentabilidad por campaña": "Rentabilité par campagne",
    "Visión clara de ingresos, gastos y márgenes por explotación.": "Vue claire des revenus, dépenses et marges par exploitation.",
    "Importación y exportación coherentes": "Importation et exportation cohérentes",
    "Procesos CSV consistentes para mover datos con menos fricción.": "Processus CSV cohérents pour déplacer les données avec moins de friction.",
    "Seguimiento operativo": "Suivi opérationnel",
    "Parcelas, riego y actividad reciente en una sola aplicación.": "Parcelles, irrigation et activité récente dans une seule application.",
    "Acceso seguro": "Accès sécurisé",
    "Accede a tu panel para revisar campañas, movimientos y estado de la explotación.": "Accédez à votre tableau de bord pour consulter les campagnes, mouvements et l'état de l'exploitation.",
    "Cuenta creada correctamente. Ya puedes iniciar sesión.": "Compte créé avec succès. Vous pouvez maintenant vous connecter.",
    "Usuario": "Utilisateur",
    "Contraseña": "Mot de passe",
    "Entrar": "Entrer",
    "¿No tienes cuenta?": "Vous n'avez pas de compte ?",
    "Crear una nueva": "En créer un nouveau",
    "Cuenta individual": "Compte individuel",
    "Crea un espacio propio para tu explotación.": "Créez un espace dédié à votre exploitation.",
    "Cada usuario mantiene sus parcelas, campañas y movimientos de forma independiente, con una experiencia más ordenada desde el primer acceso.": "Chaque utilisateur conserve ses parcelles, campagnes et mouvements de manière indépendante, avec une expérience plus ordonnée dès le premier accès.",
    "Datos separados por usuario": "Données séparées par utilisateur",
    "Cada explotación conserva su propio contexto de gestión.": "Chaque exploitation conserve son propre contexte de gestion.",
    "Estructura preparada para crecer": "Structure prête à grandir",
    "Parcelas, gastos, ingresos y riego conectados en la misma vista operativa.": "Parcelles, dépenses, revenus et irrigation connectés dans la même vue opérationnelle.",
    "Alta de usuario": "Création d'utilisateur",
    "Cada usuario tiene sus propios datos de parcelas, gastos e ingresos.": "Chaque utilisateur dispose de ses propres données de parcelles, dépenses et revenus.",
    "Apellidos": "Nom de famille",
    "Nombre de usuario": "Nom d'utilisateur",
    "Mínimo 8 caracteres.": "Minimum 8 caractères.",
    "Confirmar contraseña": "Confirmer le mot de passe",
    "¿Ya tienes cuenta?": "Vous avez déjà un compte ?",
    "Inicia sesión": "Connectez-vous",
    "Administración": "Administration",
    "Crear Nuevo Usuario": "Créer un nouvel utilisateur",
    "Alta de cuentas con nombre completo, credenciales y nivel de acceso.": "Création de comptes avec nom complet, identifiants et niveau d'accès.",
    "Rol": "Rôle",
    "Administrador": "Administrateur",
    "Crear Usuario": "Créer un utilisateur",
    "Editar Usuario": "Modifier l'utilisateur",
    "Actualiza los datos de perfil y el rol de acceso del usuario.": "Mettez à jour les données de profil et le rôle d'accès de l'utilisateur.",
    "Estado:": "État :",
    "Activo": "Actif",
    "Desactivado": "Désactivé",
    "Guardar Cambios": "Enregistrer les modifications",
    "Gestión de Usuarios": "Gestion des utilisateurs",
    "Control de usuarios, roles y estado de acceso.": "Contrôle des utilisateurs, rôles et état d'accès.",
    "No puedes desactivar tu propia cuenta.": "Vous ne pouvez pas désactiver votre propre compte.",
    "Estado": "État",
    "Creado": "Créé",
    "Tú": "Vous",
    "Desactivar": "Désactiver",
    "Activar": "Activer",
    "No hay usuarios aún.": "Il n'y a pas encore d'utilisateurs.",
    "Volver al listado": "Retour à la liste",
    "Este usuario ha sido desactivado. Por favor, contacta con el administrador si necesitas reactivar tu cuenta.": "Cet utilisateur a été désactivé. Veuillez contacter l'administrateur si vous devez réactiver votre compte.",
    "Usuario o contraseña incorrectos.": "Nom d'utilisateur ou mot de passe incorrect.",
    "El email no tiene un formato válido.": "Le format de l'e-mail est invalide.",
    "Este email ya está registrado.": "Cet e-mail est déjà enregistré.",
    "Las contraseñas no coinciden.": "Les mots de passe ne correspondent pas.",
    "La contraseña debe tener al menos 8 caracteres.": "Le mot de passe doit contenir au moins 8 caractères.",
    "La contraseña es demasiado larga (máximo 72 bytes).": "Le mot de passe est trop long (72 octets maximum).",
    "El usuario ya existe.": "L'utilisateur existe déjà.",
    "Parcela no encontrada": "Parcelle introuvable",
    "Mapa configurado correctamente": "Carte configurée correctement",
    "Trufa registrada correctamente": "Truffe enregistrée correctement",
    "Planta no encontrada": "Plant introuvable",
    "Último registro eliminado": "Dernier enregistrement supprimé",
    "No hay registro para deshacer": "Aucun enregistrement à annuler",
    "Registro de trufa eliminado": "Enregistrement de truffe supprimé",
    "No se ha encontrado el registro": "Enregistrement introuvable",
    "La parcela no tiene plantas configuradas": "La parcelle n'a pas de plants configurés",
    "Pozo registrado correctamente": "Puits enregistré correctement",
    "Registro no encontrado": "Enregistrement introuvable",
    "Pozo actualizado correctamente": "Puits mis à jour correctement",
    "Pozo eliminado correctamente": "Puits supprimé correctement",
    "Gasto registrado correctamente": "Dépense enregistrée correctement",
    "Gasto no encontrado": "Dépense introuvable",
    "Gasto actualizado correctamente": "Dépense mise à jour correctamente",
    "Gasto eliminado correctamente": "Dépense supprimée correctement",
    "Recibo cargado correctamente": "Reçu téléversé correctement",
    "Recibo no encontrado": "Reçu introuvable",
    "Recibo eliminado correctamente": "Reçu supprimé correctement",
    "Ingreso registrado correctamente": "Revenu enregistré correctement",
    "Ingreso no encontrado": "Revenu introuvable",
    "Ingreso actualizado correctamente": "Revenu mis à jour correctement",
    "Ingreso eliminado correctamente": "Revenu supprimé correctement",
    "Riego registrado correctamente": "Irrigation enregistrée correctement",
    "Riego actualizado correctamente": "Irrigation mise à jour correctement",
    "Riego eliminado correctamente": "Irrigation supprimée correctement",
    "Parcela creada correctamente": "Parcelle créée correctement",
    "Parcela actualizada correctamente": "Parcelle mise à jour correctement",
    "Parcela eliminada correctamente": "Parcelle supprimée correctement",
    "Email": "E-mail",
    "Exportar datos": "Exporter les données",
    "Exportar datos CSV": "Exporter les données CSV",
    "Descarga tus datos en un formato consistente para backup, revisión externa o reutilización en procesos de importación.": "Téléchargez vos données dans un format cohérent pour la sauvegarde, la revue externe ou la réutilisation dans des processus d'importation.",
    "Formato compatible con importación": "Format compatible avec l'importation",
    "Exportar parcelas": "Exporter les parcelles",
    "Descarga todas tus parcelas en formato CSV semicolon-delimited y sin cabecera. Incluye tiene_riego (1/0) y config_mapa para poder reconstruir el mapa en otro entorno.": "Téléchargez toutes vos parcelles au format CSV délimité par des points-virgules et sans en-tête. Inclut tiene_riego (1/0) et config_mapa pour pouvoir reconstruire la carte dans un autre environnement.",
    "Exportar gastos": "Exporter les dépenses",
    "Descarga los gastos con el mismo orden de columnas admitido por la importación. Si un gasto no está asignado a ningún bancal, la columna bancal se exporta vacía.": "Téléchargez les dépenses avec le même ordre de colonnes que l'importation. Si une dépense n'est affectée à aucune parcelle, la colonne parcelle est exportée vide.",
    "Exportar ingresos": "Exporter les revenus",
    "Descarga los ingresos en el mismo formato de importación. El total no se exporta porque se calcula automáticamente a partir de kg y euros/kg.": "Téléchargez les revenus dans le même format d'importation. Le total n'est pas exporté car il est calculé automatiquement à partir des kg et euros/kg.",
    "Exportar riego": "Exporter l'irrigation",
    "Descarga los registros de riego en formato reutilizable para la importación. El vínculo interno con gastos no se exporta; solo se incluyen los datos funcionales del registro.": "Téléchargez les enregistrements d'irrigation dans un format réutilisable pour l'importation. Le lien interne avec les dépenses n'est pas exporté ; seules les données fonctionnelles de l'enregistrement sont incluses.",
    "Exportar pozos": "Exporter les puits",
    "Descarga los registros de pozos en formato CSV. El vínculo interno con gastos no se exporta; solo se incluyen los datos funcionales del registro.": "Téléchargez les enregistrements de puits au format CSV. Le lien interne avec les dépenses n'est pas exporté ; seules les données fonctionnelles de l'enregistrement sont incluses.",
    "Exportar producción": "Exporter la production",
    "Descarga los registros de producción activos para poder importarlos en otro entorno preservando fecha/hora, parcela, planta, peso y origen.": "Téléchargez les enregistrements de production actifs afin de pouvoir les importer dans un autre environnement en conservant la date/heure, la parcelle, le plant, le poids et l'origine.",
    "Eventos de pozos": "Événements de puits",
    "Ver pozos": "Voir les puits",
    "Pozos por planta totales": "Total de puits par plant",
    "Pozos estimados": "Puits estimés",
    "Recibo del banco": "Reçu bancaire",
    "Recibo cargado:": "Reçu téléversé :",
    "Ver recibo": "Voir le reçu",
    "Eliminar recibo": "Supprimer le reçu",
    "No hay recibo adjunto": "Aucun reçu joint",
    "PDF o imagen": "PDF ou image",
    "Máximo 5MB. Formatos: PDF, JPEG, PNG, GIF, WebP": "Maximum 5 Mo. Formats : PDF, JPEG, PNG, GIF, WebP",
    "Tipos permitidos: PDF e imágenes (JPEG, PNG, GIF, WebP). Máximo 5MB.": "Types autorisés : PDF et images (JPEG, PNG, GIF, WebP). Maximum 5 Mo.",
    "Filtrar:": "Filtrer :",
    "Todas las categorías": "Toutes les catégories",
    "Todas las personas": "Toutes les personnes",
    "Limpiar filtros": "Effacer les filtres",
    "No hay gastos que coincidan con los filtros seleccionados.": "Aucune dépense ne correspond aux filtres sélectionnés.",
    "Archivo CSV delimitado por <code>;</code>, sin cabecera, codificación UTF-8.": "Fichier CSV délimité par <code>;</code>, sans en-tête, encodage UTF-8.",
    "No hay plantas configuradas para esta parcela. Configura el mapa para empezar.": "Aucun plant n'est configuré pour cette parcelle. Configurez la carte pour commencer.",
    "Arrastra el borde inferior para cambiar filas y el borde derecho para columnas. Haz clic en una celda para marcarla como hueco.": "Faites glisser le bord inférieur pour modifier les lignes et le bord droit pour modifier les colonnes. Cliquez sur une cellule pour la marquer comme vide.",
    "Consejo: ajusta filas y columnas arrastrando el borde inferior y derecho de la cuadrícula.": "Conseil : ajustez les lignes et les colonnes en faisant glisser le bord inférieur et droit de la grille.",
    "Vista completa por campaña y bancal para identificar márgenes y tendencias de rentabilidad.": "Vue complète par campagne et parcelle pour identifier les marges et les tendances de rentabilité.",
    "Los valores muestran la rentabilidad neta (ingresos − gastos). Pase el ratón sobre cada celda para ver el desglose.": "Les valeurs indiquent la rentabilité nette (revenus − dépenses). Survolez chaque cellule pour voir le détail.",
    "No hay parcelas con sistema de riego activado. Actívalo en la configuración de la parcela.": "Aucune parcelle avec irrigation activée. Activez-la dans la configuration de la parcelle.",
    "¿Está seguro de que desea eliminar este registro? Esta acción no se puede deshacer.": "Êtes-vous sûr de vouloir supprimer cet enregistrement ? Cette action ne peut pas être annulée.",
    "Visión general de campañas, rentabilidad y actividad reciente con una presentación más sobria y clara para el trabajo diario.": "Vue d'ensemble des campagnes, de la rentabilité et de l'activité récente avec une présentation plus sobre et plus claire pour le travail quotidien.",
    "Los gastos generales (sin bancal asignado) se distribuyen proporcionalmente según el porcentaje de cada bancal.": "Les dépenses générales (sans parcelle assignée) sont réparties proportionnellement selon le pourcentage de chaque parcelle.",
    "Carga parcelas, gastos, ingresos, riego, pozos y producción con una interfaz más clara y profesional. Los archivos se procesan puntualmente y no se almacenan en el servidor.": "Chargez les parcelles, dépenses, revenus, irrigations, puits et production avec une interface plus claire et plus professionnelle. Les fichiers sont traités immédiatement et ne sont pas stockés sur le serveur.",
    "Solo son obligatorios nombre y fecha de plantación. El resto de columnas pueden omitirse o dejarse vacías.": "Seuls le nom et la date de plantation sont obligatoires. Les autres colonnes peuvent être omises ou laissées vides.",
    "Esta acción insertará todos los registros del archivo en la base de datos. Asegúrate de que el archivo no contiene duplicados.": "Cette action insérera tous les enregistrements du fichier dans la base de données. Assurez-vous que le fichier ne contient pas de doublons.",
    "Si el bancal está vacío, el gasto se registra como gasto general (sin bancal asignado).": "Si la parcelle est vide, la dépense est enregistrée comme dépense générale (sans parcelle assignée).",
    "El bancal debe existir y tener riego habilitado. Las filas que no cumplan esta condición generarán un aviso y serán omitidas.": "La parcelle doit exister et avoir l'irrigation activée. Les lignes qui ne respectent pas cette condition généreront un avertissement et seront ignorées.",
    "El bancal y la planta deben existir previamente. Las filas no válidas se omiten con aviso.": "La parcelle et le plant doivent déjà exister. Les lignes non valides sont ignorées avec un avertissement.",
    "Asistente no disponible: configura OPENAI_API_KEY en el servidor.": "Assistant indisponible : configurez OPENAI_API_KEY sur le serveur.",
    "Has superado el límite temporal de consultas al asistente. Inténtalo de nuevo en unos minutos.": "Vous avez dépassé la limite temporaire de requêtes vers l'assistant. Réessayez dans quelques minutes.",
    "La parcela no tiene sistema de riego activado": "La parcelle n'a pas le système d'irrigation activé",
    "El gasto debe pertenecer a la misma parcela y tener categoría 'Riego'": "La dépense doit appartenir à la même parcelle et avoir la catégorie 'Riego'",
    "El gasto debe pertenecer a la misma parcela y tener categoría 'Pozos'": "La dépense doit appartenir à la même parcelle et avoir la catégorie 'Pozos'",
    "No se puede regenerar el mapa: existen registros de trufas activos.": "La carte ne peut pas être régénérée car il existe des enregistrements de truffes actifs.",
    "Tipo de archivo no permitido: {content_type}. Permitidos: PDF e imágenes (JPEG, PNG, GIF, WebP)": "Type de fichier non autorisé : {content_type}. Autorisés : PDF et images (JPEG, PNG, GIF, WebP)",
    "Archivo demasiado grande. Máximo: 5MB, Tamaño actual: {size_mb:.1f}MB": "Fichier trop volumineux. Maximum : 5 Mo, taille actuelle : {size_mb:.1f} Mo",
    "Línea {line}: se esperaban 5 columnas, se encontraron {count} — omitida": "Ligne {line} : 5 colonnes étaient attendues, {count} trouvées — ignorée",
    "Línea {line}: se esperaban al menos 2 columnas, se encontraron {count} — omitida": "Ligne {line} : au moins 2 colonnes étaient attendues, {count} trouvées — ignorée",
    "Línea {line}: se esperaban al menos 3 columnas, se encontraron {count} — omitida": "Ligne {line} : au moins 3 colonnes étaient attendues, {count} trouvées — ignorée",
    "Línea {line}: se esperaban al menos 4 columnas, se encontraron {count} — omitida": "Ligne {line} : au moins 4 colonnes étaient attendues, {count} trouvées — ignorée",
    "Línea {line}: bancal '{plot}' no encontrado — importado sin bancal": "Ligne {line} : parcelle '{plot}' introuvable — importée sans parcelle",
    "Línea {line}: error al parsear los datos — omitida": "Ligne {line} : erreur d'analyse des données — ignorée",
    "Parcela '{plot}': config_mapa inválida — mapa omitido": "Parcelle '{plot}' : config_mapa invalide — carte ignorée",
    "Línea {line}: bancal vacío — omitida (el registro de pozos siempre requiere parcela)": "Ligne {line} : parcelle vide — ignorée (un enregistrement de puits nécessite toujours une parcelle)",
    "Línea {line}: bancal '{plot}' no encontrado — omitida": "Ligne {line} : parcelle '{plot}' introuvable — ignorée",
    "Línea {line}: bancal vacío — omitida (el riego siempre requiere parcela)": "Ligne {line} : parcelle vide — ignorée (l'irrigation nécessite toujours une parcelle)",
    "Línea {line}: bancal '{plot}' no tiene riego habilitado — omitida": "Ligne {line} : la parcelle '{plot}' n'a pas l'irrigation activée — ignorée",
    "Línea {line}: bancal vacío — omitida": "Ligne {line} : parcelle vide — ignorée",
    "Línea {line}: planta vacía — omitida": "Ligne {line} : plant vide — ignoré",
    "Línea {line}: planta '{plant}' no encontrada en bancal '{plot}' — omitida": "Ligne {line} : plant '{plant}' introuvable dans la parcelle '{plot}' — ignoré",
    "El mapa tiene {actual} plantas pero la parcela declara {expected}. Revisa la configuración del mapa.": "La carte comporte {actual} plants mais la parcelle en déclare {expected}. Vérifiez la configuration de la carte.",
    "¿Eliminar el recibo?": "Supprimer le reçu ?",
}


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    fill_locale(root / "locales" / "en" / "LC_MESSAGES" / "messages.po", EN)
    fill_locale(root / "locales" / "fr" / "LC_MESSAGES" / "messages.po", FR)


if __name__ == "__main__":
    main()
