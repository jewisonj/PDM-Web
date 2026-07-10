-- Reference copy of remote migration `design_book_sections_partial_code_unique`.
--
-- A retired section keeps its row (rev history, reinstatement) but must not
-- block a different identity from adopting its printed section_code (e.g. a
-- station_code edit re-keys a work package that renders to the same I-SAW-1).
-- Uniqueness is only meaningful among CURRENT sections.
-- (Found by the Phase 2 adversarial review, finding M4.)

ALTER TABLE design_book_sections DROP CONSTRAINT design_book_sections_book_id_section_code_key;
CREATE UNIQUE INDEX design_book_sections_current_code_key
  ON design_book_sections(book_id, section_code)
  WHERE status = 'current';
