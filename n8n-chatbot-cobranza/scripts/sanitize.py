#!/usr/bin/env python3
"""
Sanitiza exportaciones de n8n para publicarlas en un portafolio.

Uso:
    python scripts/sanitize.py --input raw/ --output workflows/

Qué hace:
- Quita pinData, meta (instanceId), versionId, tags, credenciales y webhookIds.
- Reasigna IDs de workflow de forma determinista y re-enlaza los sub-workflows,
  para que `n8n import:workflow --separate` los conecte solos.
- Reemplaza dominios, cuentas, IDs de Google Sheets, teléfonos y marcas por
  placeholders o variables de entorno ($env.*).
- Al final busca fugas; si encuentra alguna, termina con error y no publica nada.

Si exportas flujos nuevos con otros datos sensibles, agrégalos a
REPLACEMENTS y a LEAK_PATTERNS.
"""
import argparse
import base64
import binascii
import hashlib
import json
import re
import string
import sys
from pathlib import Path

# ---------- Reemplazos de texto (el orden importa) ----------
CHATWOOT_DOMAIN = "https://chatwoot.beloz-backend.com"

REPLACEMENTS = [
    (r"ABDZ COMERZA", "EMPRESA DEMO"),
    (r"Beloz-fi", "FinDemo"),
    (r"BELOZ", "FINDEMO"),
    (r"Beloz", "FinDemo"),
    (r"beloz", "findemo"),
    (r"\bFito\b", "Finny"),
    (r"Arcus", "PayProvider"),
    (r"arcus", "payprovider"),
    (r"Finch", "BankProvider"),
    (r"finch", "bankprovider"),
    (r"\bMBL\b", "ALT_SEGMENT"),
    (r"\bmbl\b", "alt_segment"),
    # Cuentas bancarias (CLABE de 18 dígitos) y proveedores
    (r"\b\d{18}\b", "000000000000000000"),
    (r"FINCO PAY", "BANCO DEMO"),
    (r"BZ-02-", ""),
    # Nombres reales de agentes humanos -> genéricos
    (r"Giuliano Rodriguez", "Agente 5"),
    (r"\bGiuliana\b", "Agente 1"),
    (r"Juan Jose", "Agente 2"),
    (r"Nancy Pérez", "Agente 3"),
    (r"Carla Davila", "Agente 4"),
    (r"\bMarcel\b", "Agente 6"),
    (r"Tannya Estrada", "Agente 8"),
    (r"Alejandro Mayen", "Agente 9"),
    (r"\bTannya\b", "el equipo de cobranza"),
    # Teléfonos
    (r"\+52 ?55 ?9225 ?1996", "+52 55 0000 0000"),
    (r"\+?525592251996", "+525500000000"),
    (r"56 ?3754 ?6587", "55 1111 1111"),
    (r"5592251995", "5500000001"),
    (r"5295122 ?04485", "5500000002"),
    # Google Sheets
    (r"spreadsheets/d/[A-Za-z0-9_-]{20,}", "spreadsheets/d/YOUR_SPREADSHEET_ID"),
    (r"gid=\d+", "gid=0"),
]

# Patrones que NO deben aparecer en la salida
LEAK_PATTERNS = [r"(?i)beloz", r"(?i)arcus", r"(?i)finch", r"ABDZ",
                 r"9225", r"3754", r"1H0oHCX8q62e", r"1QAMWyQYVBHub9",
                 r"Nancy", r"Carla", r"Giulian", r"Tannya", r"Mayen", r"Davila",
                 r"\bMarcel\b", r"Juan Jose", r"Alejandro",
                 r"(?i)\bmbl\b", r"734180", r"04485", r"5592251", r"FINCO PAY", r"(?<!\d)\d{18}(?!\d)(?<!0{18})"]

# IDs reales de agentes en Chatwoot -> IDs ficticios (26 era el usuario bot)
AGENT_ID_MAP = {85: 1, 86: 2, 12: 3, 23: 4, 88: 5, 42: 6, 22: 7, 13: 8, 285: 10, 26: 99}

# Nombre interno del workflow -> nombre público
RENAME = {"BZ-02-Buffer-Memory": "buffer_memory", "MBL": "alt_segment",
          "PROYECTO_CONVERSATION_TABLE": "archive_data_tables",
          "daily_stuff": "daily_metrics"}

# Orden lógico del pipeline (define el prefijo del archivo)
# Chatbot: 01-14 · Monitoreo y dashboard: 20+
ORDER = {
    "first_flow": 1, "first_message": 2, "buffer_memory": 3, "agente_orquestador": 4,
    "ROUTE_BY_STATE": 5, "actived_loan": 6, "PAID_OFF": 7, "event": 8,
    "IMG_subflujo": 9, "ESCALATE_HUMAN": 10, "FALLBACK": 11, "UNSAFE": 12,
    "clasificar_intencion": 13, "tokens": 14, "alt_segment": 15,
    "status_agent": 20, "archive_data_tables": 21, "daily_metrics": 22, "dashboard": 23,
}

# Path público de cada webhook
WEBHOOK_PATHS = {"first_flow": "chatwoot-incoming", "dashboard": "dashboard"}

# Nombre de credencial -> etiqueta genérica para la documentación
CRED_LABELS = {
    "production": "BD principal, solo lectura",
    "DWH": "data warehouse, solo lectura",
    "chatwoot": "BD de Chatwoot",
    "n8n account": "API de la propia instancia de n8n",
}


def new_id(name: str) -> str:
    """ID de 16 caracteres, estable para un mismo nombre."""
    alphabet = string.ascii_letters + string.digits
    h = int(hashlib.sha256(f"portfolio:{name}".encode()).hexdigest(), 16)
    out = ""
    for _ in range(16):
        h, r = divmod(h, len(alphabet))
        out += alphabet[r]
    return out


def map_ids(text: str) -> str:
    return re.sub(r"\d+", lambda m: str(AGENT_ID_MAP.get(int(m.group()), m.group())), text)


def scrub_b64(s: str) -> str:
    """Decodifica bloques base64 largos (p. ej. plantillas HTML), los limpia y los re-codifica."""
    def repl(m):
        blob = m.group()
        try:
            txt = base64.b64decode(blob, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return blob
        return base64.b64encode(scrub_text(txt, decode_b64=False).encode("utf-8")).decode()
    return re.sub(r"[A-Za-z0-9+/]{400,}={0,2}", repl, s)


def scrub_text(s: str, decode_b64: bool = True) -> str:
    if decode_b64:
        s = scrub_b64(s)
    # IDs de agentes en arreglos de código y en SQL
    s = re.sub(r"(const (?:agents|AGENT_IDS)\s*=\s*\[)([^\]]*)(\])",
               lambda m: m.group(1) + map_ids(m.group(2)) + m.group(3), s)
    s = re.sub(r"\b((?:assignee_id|user_id)\s*=\s*)(\d+)\b",
               lambda m: m.group(1) + map_ids(m.group(2)), s)
    s = re.sub(r"\b((?:assignee_id|user_id)\s+IN\s*\()([\d,\s]+)(\))",
               lambda m: m.group(1) + map_ids(m.group(2)) + m.group(3), s, flags=re.I)
    if CHATWOOT_DOMAIN in s:
        s = s.replace(CHATWOOT_DOMAIN, "{{ $env.CHATWOOT_URL }}")
        s = s.replace("/api/v1/accounts/1/",
                      "/api/v1/accounts/{{ $env.CHATWOOT_ACCOUNT_ID }}/")
        if not s.startswith("="):
            s = "=" + s
    for pat, rep in REPLACEMENTS:
        s = re.sub(pat, rep, s)
    return s


def walk(obj):
    if isinstance(obj, dict):
        # las llaves también: en "connections" son nombres de nodos
        return {scrub_text(k): walk(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [walk(v) for v in obj]
    if isinstance(obj, str):
        return scrub_text(obj)
    return obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="raw")
    ap.add_argument("--output", default="workflows")
    ap.add_argument("--docs", default="docs/WORKFLOWS.md")
    a = ap.parse_args()

    raw = [json.loads(p.read_text(encoding="utf-8"))
           for p in sorted(Path(a.input).glob("*.json"))]
    if not raw:
        sys.exit(f"No hay archivos .json en {a.input}/")

    id2name, forbidden = {}, set()
    for wf in raw:
        id2name[wf["id"]] = RENAME.get(wf["name"], wf["name"])
        forbidden.add(wf["id"])
        inst = wf.get("meta", {}).get("instanceId")
        if inst:
            forbidden.add(inst)
    exported = set(id2name.values())
    missing, catalog = {}, []

    out_dir = Path(a.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        old.unlink()

    for wf in raw:
        name = RENAME.get(wf["name"], wf["name"])
        calls, creds = [], set()
        for n in wf["nodes"]:
            for ctype, c in (n.pop("credentials", None) or {}).items():
                forbidden.add(c["id"])
                label = CRED_LABELS.get(c["name"])
                creds.add(ctype + (f" ({label})" if label else ""))
            n.pop("webhookId", None)
            p = n.get("parameters", {})

            if n["type"] == "n8n-nodes-base.webhook":
                p["path"] = WEBHOOK_PATHS.get(name, name)
            if n["type"] == "n8n-nodes-base.twilio":
                p["from"] = "={{ $env.TWILIO_FROM_NUMBER }}"

            wid = p.get("workflowId")
            if isinstance(wid, dict) and wid.get("value"):
                target = id2name.get(wid["value"]) or RENAME.get(
                    wid.get("cachedResultName"), wid.get("cachedResultName"))
                forbidden.add(wid["value"])
                if target not in exported:
                    missing.setdefault(target, set()).add(name)
                nid = new_id(target)
                p["workflowId"] = {"__rl": True, "mode": "list", "value": nid,
                                   "cachedResultUrl": f"/workflow/{nid}",
                                   "cachedResultName": target}
                calls.append(target)

            dt = p.get("dataTableId")
            if isinstance(dt, dict):
                if dt.get("value"):
                    forbidden.add(dt["value"])
                p["dataTableId"] = {"__rl": True, "mode": "list",
                                    "value": "CONFIGURE_ME",
                                    "cachedResultName": dt.get("cachedResultName", "")}

        clean = walk({
            "name": name,
            "nodes": wf["nodes"],
            "connections": wf["connections"],
            "settings": {
                "executionOrder": wf.get("settings", {}).get("executionOrder", "v1"),
                "timezone": "America/Mexico_City",
            },
            "pinData": {},
        })
        clean["name"] = name
        clean["id"] = new_id(name)
        clean["active"] = False

        idx = ORDER.get(name, 99)
        fname = f"{idx:02d}_{name}.json"
        (out_dir / fname).write_text(
            json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        trig = next((n["type"].split(".")[-1] for n in wf["nodes"]
                     if "Trigger" in n["type"] or n["type"].endswith(".webhook")), "-")
        catalog.append((idx, fname, len(wf["nodes"]), trig,
                        sorted(set(calls)), sorted(creds)))

    # ---------- Verificación de fugas ----------
    patterns = LEAK_PATTERNS + [re.escape(x) for x in forbidden]
    leaks = []
    for f in sorted(out_dir.glob("*.json")):
        t = f.read_text(encoding="utf-8")
        # también revisa el contenido decodificado de bloques base64
        for blob in re.findall(r"[A-Za-z0-9+/]{400,}={0,2}", t):
            try:
                t += "\n" + base64.b64decode(blob, validate=True).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError, ValueError):
                pass
        for pat in patterns:
            if re.search(pat, t):
                leaks.append((f.name, pat))
    if leaks:
        print("❌ Posibles fugas encontradas (no publiques nada):")
        for fname, pat in leaks:
            print(f"   {fname}: {pat}")
        sys.exit(1)

    # ---------- Catálogo ----------
    lines = [
        "# Catálogo de workflows", "",
        "Generado automáticamente por `scripts/sanitize.py`.", "",
        "| # | Archivo | Nodos | Disparador | Llama a | Credenciales |",
        "|---|---|---|---|---|---|",
    ]
    for idx, fname, nn, trig, calls, creds in sorted(catalog):
        lines.append(f"| {idx:02d} | `{fname}` | {nn} | {trig} | "
                     f"{', '.join(calls) or '-'} | {'<br>'.join(creds) or '-'} |")
    if missing:
        lines += ["", "## Sub-workflows referenciados que aún no están en el repo", ""]
        for m, by in sorted(missing.items()):
            lines.append(f"- `{m}` (llamado desde: {', '.join(sorted(by))})")
    Path(a.docs).parent.mkdir(parents=True, exist_ok=True)
    Path(a.docs).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"✅ {len(raw)} workflows sanitizados en {out_dir}/ sin fugas detectadas.")
    if missing:
        print("⚠️  Referenciados pero no exportados:", ", ".join(sorted(missing)))


if __name__ == "__main__":
    main()
