#!/usr/bin/env python3
"""
Ensayo automático del guion de demostración (REQUISITOS.md, sección 6).

Abre cuatro ventanas a la vez (médico, especialista, contable y admin), como
en la sustentación, y comprueba que cada reacción aparece SIN RECARGAR la
página. Al final verifica que ninguna ventana se recargó.

Modos:
  --modo simulado   (por defecto) dispara los eventos con el panel de
                    demostración del front. Sirve mientras el canal en vivo
                    y los módulos del Corte 2 no estén listos.
  --modo real       hace las acciones de verdad contra la API: bloqueo por
                    3 intentos y desbloqueo por el admin. Los pasos que
                    dependen de módulos aún no construidos se reportan como
                    pendientes, no como fallas.

Uso:
    pip install playwright && playwright install chromium   (fuera de este contenedor)
    python scripts/demo_e2e.py --url http://localhost:5173
    python scripts/demo_e2e.py --url https://xxxx.trycloudflare.com --modo real --ver
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid

from playwright.async_api import Page, async_playwright, expect

ESPERA_MS = 8000          # R17: el evento debe llegar en menos de 8 s
resultados: list[tuple[str, str]] = []


def anotar(estado: str, texto: str) -> None:
    resultados.append((estado, texto))
    print(f"  {estado:<9} {texto}", flush=True)


async def entrar(navegador, base: str, usuario: str, clave: str) -> Page:
    ctx = await navegador.new_context(viewport={"width": 1366, "height": 900}, locale="es-CO")
    pagina = await ctx.new_page()
    await pagina.goto(f"{base}/login")
    await pagina.fill("#usuario", usuario)
    await pagina.fill("#clave", clave)
    await pagina.click("button[type=submit]")
    await pagina.wait_for_url("**/app/**", timeout=20000)
    # Marca en memoria: si la página se recarga, desaparece.
    marca = uuid.uuid4().hex
    await pagina.evaluate("m => { window.__marcaSinRecarga = m; }", marca)
    pagina._marca = marca  # type: ignore[attr-defined]
    return pagina


async def simular(pagina: Page, boton: str) -> None:
    panel = pagina.get_by_role("complementary", name="Panel de demostración")
    if not await panel.is_visible():
        await pagina.keyboard.press("Control+Shift+D")
    await panel.get_by_role("button", name=boton).click()


async def paso(nombre: str, coro) -> None:
    try:
        await coro
        anotar("PASA", nombre)
    except Exception as e:  # noqa: BLE001
        anotar("FALLA", f"{nombre}: {type(e).__name__}: {str(e).splitlines()[0][:140]}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.getenv("DEMO_URL", "http://localhost:5173"))
    ap.add_argument("--clave", default=os.getenv("DEMO_PASSWORD", "Demo#Hospital2026"))
    ap.add_argument("--modo", choices=["simulado", "real"], default="simulado")
    ap.add_argument("--ver", action="store_true", help="mostrar las ventanas (no headless)")
    a = ap.parse_args()
    base = a.url.rstrip("/")

    async with async_playwright() as p:
        nav = await p.chromium.launch(headless=not a.ver)
        print(f"Abriendo 4 ventanas contra {base} (modo {a.modo})")
        medico = await entrar(nav, base, "medico01", a.clave)
        especialista = await entrar(nav, base, "especialista01", a.clave)
        contable = await entrar(nav, base, "contable01", a.clave)
        admin = await entrar(nav, base, "admin", a.clave)

        print("\n[1] Alerta crítica en la ventana del médico")
        if a.modo == "simulado":
            await simular(medico, "Alerta crítica")
        else:
            anotar("PENDIENTE", "requiere el análisis de IA real (Esteban) y el canal en vivo (José David)")
        if a.modo == "simulado":
            banner = medico.get_by_label("Alertas críticas activas")
            await paso("La alerta aparece sola", expect(banner).to_be_visible(timeout=ESPERA_MS))
            await paso("Muestra la cuenta regresiva del escalamiento",
                       expect(banner.get_by_text("Se escala al administrador")).to_be_visible(timeout=ESPERA_MS))

            print("\n[2] Reconocer la alerta con una nota")
            await medico.get_by_placeholder("Conducta tomada").first.fill("Se reserva cama UCI")
            await medico.get_by_role("button", name="Reconocer", exact=True).first.click()
            await paso("La alerta desaparece al reconocerla", expect(banner).to_be_hidden(timeout=ESPERA_MS))

            print("\n[3] Factura automática en la ventana del contable")
            await simular(contable, "Factura automática")
            await paso("La factura automática aparece sin recargar",
                       expect(contable.get_by_text("Automática").first).to_be_visible(timeout=ESPERA_MS))

            print("\n[4] Remisión en la ventana del especialista")
            antes = await especialista.get_by_role("button", name="Aceptar").count()
            await simular(especialista, "Llega una remisión")
            await paso("La remisión nueva aparece sin recargar",
                       expect(especialista.get_by_role("button", name="Aceptar")).to_have_count(antes + 1, timeout=ESPERA_MS))
            await especialista.get_by_role("button", name="Aceptar").first.click()
            await paso("Aceptarla la saca de pendientes",
                       expect(especialista.get_by_role("button", name="Aceptar")).to_have_count(antes, timeout=ESPERA_MS))

            print("\n[5] Evento FHIR en la ventana del médico")
            await simular(medico, "Glucosa desde FHIR")
            await paso("El aviso de FHIR llega a la bandeja",
                       expect(medico.locator("button[aria-label^='Bandeja de avisos']")).not_to_have_attribute(
                           "aria-label", "Bandeja de avisos: 0 sin leer", timeout=ESPERA_MS))

        print("\n[6] Bloqueo por 3 intentos y desbloqueo por el admin")
        if a.modo == "real":
            ctx = await nav.new_context()
            intruso = await ctx.new_page()
            for _ in range(3):
                await intruso.goto(f"{base}/login")
                await intruso.fill("#usuario", "bloqueo_prueba")
                await intruso.fill("#clave", "clave-equivocada")
                await intruso.click("button[type=submit]")
                await intruso.wait_for_timeout(600)
            await paso("El login muestra la cuenta bloqueada",
                       expect(intruso.get_by_text("Cuenta bloqueada", exact=False).first).to_be_visible(timeout=ESPERA_MS))
            if "/app/admin" not in admin.url:
                await admin.goto(f"{base}/app/admin")
            await admin.get_by_role("tab", name="Cuentas bloqueadas").click()
            fila = admin.get_by_role("listitem").filter(has_text="bloqueo_prueba")
            await paso("El admin ve la cuenta bloqueada", expect(fila).to_be_visible(timeout=15000))

            async def desbloquear():
                await fila.get_by_role("button", name="Desbloquear").click(timeout=ESPERA_MS)
                await expect(fila).to_be_hidden(timeout=ESPERA_MS)
            await paso("El admin la desbloquea", desbloquear())
            await ctx.close()
        else:
            await simular(admin, "Cuenta bloqueada")
            await paso("El admin recibe el aviso del bloqueo",
                       expect(admin.get_by_text("quedó bloqueada").first).to_be_visible(timeout=ESPERA_MS))

        print("\n[7] Ninguna ventana se recargó")
        for nombre, pg in [("médico", medico), ("especialista", especialista), ("contable", contable), ("admin", admin)]:
            if nombre == "admin" and a.modo == "real":
                continue  # en modo real el admin navega a propósito a su panel
            sigue = await pg.evaluate("() => window.__marcaSinRecarga") == pg._marca  # type: ignore[attr-defined]
            anotar("PASA" if sigue else "FALLA", f"Sin recargas en la ventana del {nombre}")

        await nav.close()

    fallas = sum(1 for e, _ in resultados if e == "FALLA")
    pendientes = sum(1 for e, _ in resultados if e == "PENDIENTE")
    print(f"\nRESULTADO: {len(resultados) - fallas - pendientes} pasan, {fallas} fallan, {pendientes} pendientes")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
