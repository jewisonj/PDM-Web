-- Rename items.needs_dxf -> items.auto_flatten
--
-- The flag never meant "this part has / needs a DXF". It only marks sheet metal
-- parts whose flat pattern should be generated from STEP by the FreeCAD worker
-- (set by the "Generate DXF" button, re-queued on STEP upload). Plate parts with
-- DXFs exported straight from CAD should leave it false.
--
-- Deploy together with the backend code that reads auto_flatten: stop the
-- backend, apply this, then start the updated backend.

alter table public.items rename column needs_dxf to auto_flatten;

comment on column public.items.auto_flatten is
  'Sheet metal part: generate DXF/SVG flat pattern from STEP with FreeCAD (auto-queued on STEP upload). Not required for a part to have a DXF.';
