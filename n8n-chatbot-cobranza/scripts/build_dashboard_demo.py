#!/usr/bin/env python3
"""
Genera una versión estática del dashboard con datos ficticios, lista para
GitHub Pages.

Toma la plantilla HTML embebida (base64) en workflows/23_dashboard.json,
le inyecta un payload simulado con la misma forma que arma el workflow
y la guarda en <raíz del repo>/docs/n8n-chatbot-cobranza/dashboard-demo/index.html.

Uso:
    python scripts/build_dashboard_demo.py
"""
import base64
import json
import random
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / "workflows" / "23_dashboard.json"
# GitHub Pages se sirve desde la carpeta docs/ en la raíz del repo "automations"
REPO_ROOT = ROOT.parent
OUT = REPO_ROOT / "docs" / ROOT.name / "dashboard-demo" / "index.html"

AGENTS = [(1, "Agente 1"), (2, "Agente 2"), (3, "Agente 3"),
          (4, "Agente 4"), (5, "Agente 5"), (6, "Agente 6")]
DAYS = 21


def load_template() -> str:
    wf = json.loads(WF.read_text(encoding="utf-8"))
    code = next(n["parameters"]["jsCode"] for n in wf["nodes"]
                if "TEMPLATE_B64" in n.get("parameters", {}).get("jsCode", ""))
    b64 = re.search(r'TEMPLATE_B64 = "([^"]+)"', code).group(1)
    return base64.b64decode(b64).decode("utf-8")


def mock_payload(seed: int = 7) -> dict:
    rnd = random.Random(seed)
    today = date.today()
    daily, cierres, tokens, ignorados, escalaciones, agentes_dia = [], [], [], [], [], []

    for i in range(DAYS, 0, -1):
        f = (today - timedelta(days=i)).isoformat()
        weekday = (today - timedelta(days=i)).weekday()
        entradas = rnd.randint(260, 380) if weekday < 5 else rnd.randint(120, 190)
        bot = int(entradas * rnd.uniform(0.62, 0.78))
        sin = rnd.randint(3, 12)
        hum = entradas - bot - sin
        daily.append({"fecha": f, "entradas": entradas, "resueltas_bot": bot,
                      "terminadas_con_humano": hum, "sin_asignar": sin,
                      "cobertura_bot": round(bot / entradas, 4)})

        cierres.append({"fecha": f, "cerradas_bot": bot - rnd.randint(0, 8),
                        "cerradas_humano": hum - rnd.randint(0, 6),
                        "cerradas_sistema": rnd.randint(2, 15),
                        "total_cierres": entradas})

        costo = round(entradas * rnd.uniform(0.0035, 0.0055), 2)
        tokens.append({"fecha": f, "costo_total_usd": costo,
                       "costo_por_conversacion_usd": round(costo / entradas, 4)})

        ign = rnd.randint(8, 30)
        ignorados.append({"fecha": f, "total_ignorados": ign,
                          "conversaciones_unicas": ign - rnd.randint(0, 5)})

        esc_u = max(1, hum - rnd.randint(5, 20))
        escalaciones.append({"fecha": f, "total_escalaciones": esc_u + rnd.randint(0, 10),
                             "conversaciones_unicas": esc_u})

        row = {"fecha": f}
        reparto = [rnd.random() for _ in AGENTS]
        total_r = sum(reparto)
        for (aid, name), r in zip(AGENTS, reparto):
            row[name] = int(hum * r / total_r)
        row.update({"agente n8n": bot, "sin asignar": sin, "Total general": entradas})
        agentes_dia.append(row)

    now = datetime.now(timezone.utc)
    agentes = [{"agent_id": aid, "name": name,
                "status": "online" if aid in (1, 3, 4, 6) else "offline",
                "update_at": (now - timedelta(minutes=rnd.randint(2, 240))).isoformat()}
               for aid, name in AGENTS]
    ayer = (today - timedelta(days=1)).isoformat()
    conexion = [{"fecha": ayer, "agent_id": aid, "horas_conectado": round(rnd.uniform(5.5, 9.0), 2)}
                for aid, _ in AGENTS]

    return {"generated_at": now.isoformat(), "daily": daily, "cierres": cierres,
            "tokens": tokens, "ignorados": ignorados, "escalaciones": escalaciones,
            "agentes": agentes, "agentes_dia": agentes_dia, "conexion": conexion}


BANNER = ('<div style="background:#16181D;color:#F1F2EE;font:500 12px/1.4 Inter,system-ui,sans-serif;'
          'padding:8px 16px;text-align:center">Demo con datos ficticios · en producción este '
          'dashboard lo sirve un webhook de n8n con datos reales de Chatwoot y Google Sheets</div>')


def main():
    html = load_template().replace("__EMBEDDED_DATA__", json.dumps(mock_payload(), ensure_ascii=False))
    html = re.sub(r"(<body[^>]*>)", r"\1" + BANNER, html, count=1)
    # en la demo estática no hay webhook al cual refrescar
    html = html.replace("setInterval(refresh,3600000);", "")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"✅ Demo generada en {OUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
