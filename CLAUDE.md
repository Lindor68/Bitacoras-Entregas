# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Bitacoras-Entregas is a bitácora (log) for tracking logistics trips and deliveries. Hierarchy:
`viaje` (trip) → several `establecimiento`s visited → several `documento`s per visit → several `producto` line
items per document → one or more `lote`s (batch/expiry) per line item. The app tracks three independent status
dimensions — `estado_viaje`, `estado_documento`, `estado_entrega` — plus a full audit trail.

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
  `viaje_establecimiento`, `documento`, `documento_producto`, `documento_producto_lote`), and `auditoria` (audit
  log). `establecimiento.codigo` and `producto.sku` are the optional-but-unique business identifiers — `nombre` is
  deliberately **not** unique on either table, so all UI selectors resolve by `id`, never by name. Lot/expiry
  (`lote`, `fecha_vencimiento`) live on `documento_producto_lote`, never on the `producto` catalog, since the same
  product arrives in different batches on different deliveries.
- `db.py` — connection helper, `init_db()`, and the only write paths: `insertar`, `actualizar`, `anular`,
  `anular_documento`. Every write logs a row in `auditoria` (`CREACION`/`MODIFICACION`/`ANULACION`). **No table is
  ever deleted from** — "eliminar" in the UI always means logical deactivation: business tables with their own
  lifecycle status (`viaje`, `documento`) get anulado via that status (`estado_viaje='Cancelado'`,
  `estado_documento='Anulado'`); pure catalogs and detail tables get anulado via an `activo` flag. `anular()`
  requires both `usuario_id` and a non-empty `motivo`, which is stored in `auditoria.detalle`.
  `anular_documento()` additionally enforces business coherence: a document whose `estado_entrega='Entregado'`
  cannot be anulled directly (the delivery must first be corrected/reversed via the edit form), and anulling a
  document cascades a logical deactivation to its still-active `documento_producto` lines and their
  `documento_producto_lote` rows, each with its own audit entry.
  All timestamps are stored in **UTC** (`datetime('now')` in SQL, `datetime.now(timezone.utc)` in Python);
  `db.formatear_fechas_local()` converts to local time only for display, never for storage. Table/column names used
  in the generic `insertar`/`actualizar`/`anular` helpers are validated against a whitelist (`TABLAS_PERMITIDAS`,
  `_columnas()`) before being interpolated into SQL — only values travel as `?` parameters.
- `common.py` — `seleccionar_usuario_actual()` (sidebar "usuario actual", no authentication yet; populates
  `creado_por`/`modificado_por` and the audit log's `usuario` field), `seleccionar_por_id()` (id-based selectbox
  helper used everywhere instead of matching by name), and `ejecutar_con_manejo()` (wraps every write call so
  `sqlite3.IntegrityError` / `db.ErrorNegocio` show a friendly `st.error()` instead of crashing the page).
- `pages/` — one screen per entity (Viajes, Establecimientos, Documentos+Productos+Lotes, Productos,
  Importar/Exportar).

No automated tests yet. There are no lint/build commands beyond running the app.
