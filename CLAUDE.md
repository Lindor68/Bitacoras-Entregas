# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Bitacoras-Entregas is a bitácora (log) for tracking logistics trips and deliveries. The **document/folio is the
primary unit of tracking**. Hierarchy: `viaje` (trip) → several `establecimiento`s visited → several
`documento`s (folios) per visit → delivery result (`documento.estado_documento`). Products are **not** registered
as a matter of course — a product only gets a row when there's a discrepancy detected at destination (shortage,
damage, expiry, wrong batch, etc.), captured in `incidencia_producto`, linked to the document. A document may have
zero, one, or several incidents; `estado_documento` and `incidencia_producto.estado_resolucion` are deliberately
independent state machines. Full audit trail throughout.

## Stack

- **UI**: Streamlit (multipage app: `app.py` is the dashboard, `pages/*.py` are the entity screens)
- **Data**: SQLite (`data/bitacora.db`, created at runtime by `db.init_db()`, not committed to git)
- **Import/Export**: CSV/Excel via pandas + openpyxl (`pages/5_Importar_Exportar.py`) — CSV/Excel are only an
  import/export format, never the source of truth

## Running

```
pip install -r requirements.txt
streamlit run app.py
```

## Architecture

- `schema.sql` — full DDL: catalogs (`usuario`, `establecimiento`, `producto`), operational tables (`viaje`,
  `viaje_establecimiento`, `documento`, `incidencia_producto`), and `auditoria` (audit log).
  `establecimiento.codigo` and `producto.sku` are the optional-but-unique business identifiers — `nombre` is
  deliberately **not** unique on either table, so all UI selectors resolve by `id`, never by name.
  `documento.estado_documento` is a single unified field (9 values: Pendiente, Cargado, Entregado, Entregado con
  observaciones, Entrega parcial, No entregado, Rechazado, Devuelto, Anulado) — it merges what used to be two
  separate columns (administrative status + delivery outcome). `incidencia_producto` has **no FK to `producto`**:
  `producto_codigo`/`producto_descripcion` are free text, because registering a product is never a prerequisite —
  it only happens when there's an actual incident. `documento_producto` / `documento_producto_lote` from the
  earlier per-line-item model are no longer part of the active schema (see the MVP note at the top of
  `schema.sql`); they are never dropped or touched if a pre-existing database still has them.
- `db.py` — connection helper, `init_db()`, and the only write paths: `insertar`, `actualizar`, `anular`,
  `anular_documento`. Every write logs a row in `auditoria` (`CREACION`/`MODIFICACION`/`ANULACION`). **No table is
  ever deleted from** — "eliminar" in the UI always means logical deactivation: `viaje`/`documento` get anulado via
  their own status column (`estado_viaje='Cancelado'`, `estado_documento='Anulado'`); pure catalogs and
  `incidencia_producto` get anulado via an `activo` flag. `anular()` requires both `usuario_id` and a non-empty
  `motivo`, stored in `auditoria.detalle`. `anular_documento()` additionally blocks anulling a document whose
  `estado_documento='Entregado'` directly — the caller must first record a traceable correction/reversal (edit the
  status, e.g. to `Devuelto`/`Rechazado`) before anulling. Incidents are **not** touched when their parent document
  is anulled — `estado_documento` and `incidencia_producto.estado_resolucion` are independent on purpose.
  All timestamps are stored in **UTC** (`datetime('now')` in SQL, `datetime.now(timezone.utc)` in Python);
  `db.formatear_fechas_local()` converts to local time only for display, never for storage. Table/column names used
  in the generic `insertar`/`actualizar`/`anular` helpers are validated against a whitelist (`TABLAS_PERMITIDAS`,
  `_columnas()`) before being interpolated into SQL — only values travel as `?` parameters.
- `common.py` — `seleccionar_usuario_actual()` (sidebar "usuario actual", no authentication yet; populates
  `creado_por`/`modificado_por` and the audit log's `usuario` field), `seleccionar_por_id()` (id-based selectbox
  helper used everywhere instead of matching by name), and `ejecutar_con_manejo()` (wraps every write call so
  `sqlite3.IntegrityError` / `db.ErrorNegocio` show a friendly `st.error()` instead of crashing the page).
- `app.py` — no longer a page itself: it's an explicit `st.navigation()` router (Streamlit ≥1.36). The dashboard
  lives in a function (`mostrar_dashboard`) registered as its own `st.Page`. Only `app.py` may call
  `st.set_page_config()` now — the individual `pages/*.py` files must not (that would raise, since `st.navigation`
  makes `app.py` the single entry point on every rerun).
- `pages/` — `1_Viajes.py`, `2_Establecimientos.py`, `3_Documentos.py` (folio only — no product/lot section
  anymore), `4_Incidencias.py` (the only place products are ever entered), `5_Importar_Exportar.py`.
  `6_Productos.py` still exists (the `producto` catalog isn't deleted) but is **deliberately excluded** from the
  `st.navigation()` list in `app.py`, so it's unreachable from the running MVP — re-enable by adding it back to
  that list.

No automated tests yet. There are no lint/build commands beyond running the app.
