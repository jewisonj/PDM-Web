drawing_setup_file C:\PTC_Data\DTL\prodetail.dtl
format_setup_file C:\PTC_Data\DTL\prodetail.dtl
pro_unit_length unit_inch
pro_unit_mass unit_pound
template_designasm $PRO_DIRECTORY\templates\inlbs_asm_design_abs.asm
template_new_ecadasm $PRO_DIRECTORY\templates\inlbs_ecad_asm_abs.asm
template_drawing $PRO_DIRECTORY\templates\c_drawing.drw
template_sheetmetalpart $PRO_DIRECTORY\templates\inlbs_part_sheetmetal_abs.prt
template_solidpart $PRO_DIRECTORY\templates\inlbs_part_solid_abs.prt
template_boardpart $PRO_DIRECTORY\templates\inlbs_ecad_board_abs.prt
todays_date_note_format %Mmm-%dd-%yy
tolerance_standard ansi
weld_ui_standard ansi
search_path_file $CREO_COMMON_FILES\ifx\parts\prolibrary\search.pro
prehighlight_tree yes
sketcher_starts_in_2d yes
sketcher_dimension_autolock yes
dim_background legacy
save_instance_accelerator none
save_file_iterations no
mapkey md @MAPKEY_LABELMeasure Distance;\
mapkey(continued) ~ Activate `main_dlg_cur` `page_Analysis_control_btn` 1;\
mapkey(continued) ~ Command `ProCmdNaMeasureDistance` ;~ Trigger `nmd_1` `nmd_prj_lst` `0`;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_prj_lst` ``;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_setup_tbl` 2 `0` `References`;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_setup_tbl` 2 `` ``;\
mapkey(continued) ~ Move `nmd_1` `nmd_1` 2 17.705711 3.022926;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_setup_tbl` 2 `0` `ChkBtn`;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_setup_tbl` 2 `` ``;
mapkey ml @MAPKEY_LABELMeasure Length;\
mapkey(continued) ~ Activate `main_dlg_cur` `page_Analysis_control_btn` 1;\
mapkey(continued) ~ Command `ProCmdNaMeasureLength` ;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_setup_tbl` 2 `0` `References`;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_setup_tbl` 2 `` ``;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_setup_tbl` 2 `0` `References`;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_setup_tbl` 2 `` ``;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_report_tbl` 2 `0 row` `0 column`;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_report_tbl` 2 `` ``;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_report_tbl` 2 `0 row` `0 column`;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_report_tbl` 2 `` ``;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_setup_tbl` 2 `0` `References`;\
mapkey(continued) ~ Trigger `nmd_1` `nmd_setup_tbl` 2 `` ``;\
mapkey(continued) ~ Move `nmd_1` `nmd_1` 2 37.714762 -21.881568;
mapkey param @MAPKEY_LABELSend Param to Server;\
mapkey(continued) ~ Command `ProCmdMdlTreeSaveAsText` ;\
mapkey(continued) ~ Update `inputname` `InpName` \
mapkey(continued) `D:\\PDM_Vault\\CADData\\ParameterUpdate\\treetool.txt`;\
mapkey(continued) ~ Activate `inputname` `okbutton`;~ Command `ProCmdModelSave` ;\
mapkey(continued) ~ Activate `storage_conflicts` `OK_PushButton`;
mapkey csmr @MAPKEY_LABELCreate Sheetmetal Relations;\
mapkey(continued) ~ Command `ProCmdMmRels` ;~ Arm `relation_dlg` `RelText`;\
mapkey(continued) ~ Update `relation_dlg` `RelText` 1 398 591 1 `\n\ncut_length = (PRO_MP_AREA \
mapkey(continued) - ((2*PRO_MP_VOLUME )/ SMT_THICKNESS)) / SMT_THICKNESS\ncut_time = \
mapkey(continued) cut_length / (2.21*(SMT_THICKNESS^-1.39))\nPRICE_EST = (cut_time*(150/60)) + \
mapkey(continued) (PRO_MP_MASS*PRICE:MTRL)`;~ Activate `relation_dlg` `PB_OK`;\
mapkey(continued) ~ Command `ProCmdModelSave` ;~ Activate `storage_conflicts` `OK_PushButton`;
mapkey sbom @MAPKEY_LABELSend BOM to Server;\
mapkey(continued) ~ Command `ProCmdMdlTreeSaveAsText` ;\
mapkey(continued) ~ Update `inputname` `InpName` `D:\\PDM_Vault\\CADData\\BOM\\treetool.txt`;\
mapkey(continued) ~ Activate `inputname` `okbutton`;
mapkey dfwmba @MAPKEY_LABELWatts Marine DRW Format B ASM;\
mapkey(continued) ~ Command `ProCmdDwgPageSetup` ;~ Arm `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Open `pagesetup` `TblFormats_INPUT`;~ Close `pagesetup` `TblFormats_INPUT`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats_INPUT` 1 `Browse...`;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Trail `` `` `PREVIEW_POPUP_TIMER` `file_open:Ph_list.Filelist:<NULL>`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `Materials`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `Materials`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `b_form_wm_asm.frm`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `b_form_wm_asm.frm`;\
mapkey(continued) ~ Activate `pagesetup` `OK`;~ Activate `keep_format_tables` `RemoveAll`;\
mapkey(continued) ~ Activate `0_std_confirm` `OK`;
mapkey dfwmbp @MAPKEY_LABELWatts Marine DRW Format B PRT;\
mapkey(continued) ~ Command `ProCmdDwgPageSetup` ;~ Arm `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Open `pagesetup` `TblFormats_INPUT`;~ Close `pagesetup` `TblFormats_INPUT`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats_INPUT` 1 `Browse...`;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Trail `` `` `PREVIEW_POPUP_TIMER` `file_open:Ph_list.Filelist:<NULL>`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `Materials`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `Materials`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `b_form_wm.frm`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `b_form_wm.frm`;\
mapkey(continued) ~ Activate `pagesetup` `OK`;~ Activate `keep_format_tables` `RemoveAll`;\
mapkey(continued) ~ Activate `0_std_confirm` `OK`;
mapkey dfwmap @MAPKEY_LABELWatts Marine DRW Format A PRT;\
mapkey(continued) ~ Command `ProCmdDwgPageSetup` ;~ Arm `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Open `pagesetup` `TblFormats_INPUT`;~ Close `pagesetup` `TblFormats_INPUT`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats_INPUT` 1 `Browse...`;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Trail `` `` `PREVIEW_POPUP_TIMER` `file_open:Ph_list.Filelist:<NULL>`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `Materials`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `Materials`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `a_form_wm.frm`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `a_form_wm.frm`;\
mapkey(continued) ~ Activate `pagesetup` `OK`;~ Activate `keep_format_tables` `RemoveAll`;\
mapkey(continued) ~ Activate `0_std_confirm` `OK`;mapkey apsf @MAPKEY_LABELApply Sheet Format;\
mapkey(continued) ~ Command `ProCmdDwgPageSetup` ;~ Arm `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Open `pagesetup` `TblFormats_INPUT`;~ Close `pagesetup` `TblFormats_INPUT`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats_INPUT` 1 `Browse...`;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `formats`;
mapkey dfamfap @MAPKEY_LABELAMF DRW Format A PRT;\
mapkey(continued) ~ Command `ProCmdDwgPageSetup` ;~ Arm `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Open `pagesetup` `TblFormats_INPUT`;~ Close `pagesetup` `TblFormats_INPUT`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats_INPUT` 1 `Browse...`;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Trail `` `` `PREVIEW_POPUP_TIMER` `file_open:Ph_list.Filelist:<NULL>`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `Materials`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `Materials`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `a_form_amf.frm`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `a_form_amf.frm`;\
mapkey(continued) ~ Activate `pagesetup` `OK`;~ Activate `keep_format_tables` `RemoveAll`;\
mapkey(continued) ~ Activate `0_std_confirm` `OK`;mapkey apsf @MAPKEY_LABELApply Sheet Format;\
mapkey(continued) ~ Command `ProCmdDwgPageSetup` ;~ Arm `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Open `pagesetup` `TblFormats_INPUT`;~ Close `pagesetup` `TblFormats_INPUT`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats_INPUT` 1 `Browse...`;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `formats`;
mapkey dfamfbp @MAPKEY_LABELAMF DRW Format B PRT;\
mapkey(continued) ~ Command `ProCmdDwgPageSetup` ;~ Arm `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Open `pagesetup` `TblFormats_INPUT`;~ Close `pagesetup` `TblFormats_INPUT`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats_INPUT` 1 `Browse...`;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Trail `` `` `PREVIEW_POPUP_TIMER` `file_open:Ph_list.Filelist:<NULL>`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `Materials`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `Materials`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `b_form_amf.frm`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `b_form_amf.frm`;\
mapkey(continued) ~ Activate `pagesetup` `OK`;~ Activate `keep_format_tables` `RemoveAll`;\
mapkey(continued) ~ Activate `0_std_confirm` `OK`;mapkey apsf @MAPKEY_LABELApply Sheet Format;\
mapkey(continued) ~ Command `ProCmdDwgPageSetup` ;~ Arm `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Open `pagesetup` `TblFormats_INPUT`;~ Close `pagesetup` `TblFormats_INPUT`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats_INPUT` 1 `Browse...`;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `formats`;
mapkey dfamfba @MAPKEY_LABELAMF DRW Format B ASM;\
mapkey(continued) ~ Command `ProCmdDwgPageSetup` ;~ Arm `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Open `pagesetup` `TblFormats_INPUT`;~ Close `pagesetup` `TblFormats_INPUT`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats_INPUT` 1 `Browse...`;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Trail `` `` `PREVIEW_POPUP_TIMER` `file_open:Ph_list.Filelist:<NULL>`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `Materials`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `Materials`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `b_form_amf_asm.frm`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `b_form_amf_asm.frm`;\
mapkey(continued) ~ Activate `pagesetup` `OK`;~ Activate `keep_format_tables` `RemoveAll`;\
mapkey(continued) ~ Activate `0_std_confirm` `OK`;
mapkey cipdf @MAPKEY_LABELCheck In PDF;~ Close `main_dlg_cur` `appl_casc`;\
mapkey(continued) ~ Command `ProCmdModelSaveAs` ;~ Open `file_saveas` `type_option`;\
mapkey(continued) ~ Close `file_saveas` `type_option`;\
mapkey(continued) ~ Select `file_saveas` `type_option` 1 `db_617`;\
mapkey(continued) ~ Activate `file_saveas` `pb_favorites__FAV_10_`;\
mapkey(continued) ~ Activate `file_saveas` `OK`;\
mapkey(continued) ~ Trail `` `` `PREVIEW_POPUP_TIMER` `main_dlg_w2:PHTLeft.AssyTree:<NULL>`;\
mapkey(continued) ~ Select `intf_profile` `pdf_export.pdf_color_depth` 1 `pdf_color`;\
mapkey(continued) ~ Select `intf_profile` `pdf_export.pdf_color_depth` 1 `pdf_gray`;\
mapkey(continued) ~ Select `intf_profile` `pdf_export.PDFMainTab` 1 `pdf_export.PDFContent`;\
mapkey(continued) ~ Select `intf_profile` `pdf_export.pdf_font_stroke` 1 `pdf_stroke_none`;\
mapkey(continued) ~ Select `intf_profile` `pdf_export.pdf_font_stroke` 1 `pdf_stroke_all`;\
mapkey(continued) ~ Select `intf_profile` `pdf_export.PDFMainTab` 1 `pdf_export.PDFFormat`;\
mapkey(continued) ~ Activate `intf_profile` `pdf_export.pdf_launch_viewer` 1;\
mapkey(continued) ~ Activate `intf_profile` `pdf_export.pdf_launch_viewer` 0;\
mapkey(continued) ~ Activate `intf_profile` `OkPshBtn`;
mapkey fr @MAPKEY_LABELCreate Flat Representation;\
mapkey(continued) ~ Command `ProCmdSmtFlatPat` ;~ Activate `main_dlg_cur` `dashInst0.Done`;\
mapkey(continued) ~ Command `ProCmdSmtFlatPatMakeConf` ;\
mapkey(continued) ~ Input `Odui_Dlg_00` `t1.smt_make_conf_inp` `F`;\
mapkey(continued) ~ Input `Odui_Dlg_00` `t1.smt_make_conf_inp` `FL`;\
mapkey(continued) ~ Input `Odui_Dlg_00` `t1.smt_make_conf_inp` `FLA`;\
mapkey(continued) ~ Input `Odui_Dlg_00` `t1.smt_make_conf_inp` `FLAT`;\
mapkey(continued) ~ Update `Odui_Dlg_00` `t1.smt_make_conf_inp` `FLAT`;\
mapkey(continued) ~ Activate `Odui_Dlg_00` `t1.smt_make_conf_inp`;\
mapkey(continued) ~ FocusOut `Odui_Dlg_00` `t1.smt_make_conf_inp`;\
mapkey(continued) ~ Activate `Odui_Dlg_00` `stdbtn_1`;\
mapkey(continued) ~ RButtonArm `main_dlg_cur` `PHTLeft.AssyTree` `T3 15`;\
mapkey(continued) ~ PopupOver `main_dlg_cur` `PM_PHTLeft.AssyTree` 1 `PHTLeft.AssyTree`;\
mapkey(continued) ~ Open `main_dlg_cur` `PM_PHTLeft.AssyTree`;\
mapkey(continued) ~ Close `main_dlg_cur` `PM_PHTLeft.AssyTree`;\
mapkey(continued) ~ Trail `MiniToolbar` `MiniToolbar` `UIT_TRANSLUCENT` `NEED_TO_CLOSE`;\
mapkey(continued) ~ Command `ProCmdActivateInsertBefore@PopupMenuTree`;
mapkey fv @MAPKEY_LABELCreate Flat View;~ Timer `` `` `popupMenuRMBTimerCB`;\
mapkey(continued) ~ Close `rmb_popup` `PopupMenu`;\
mapkey(continued) ~ Command `ProCmdViewNormal@PopupMenuGraphicWinStack` ;\
mapkey(continued) ~ Select `main_dlg_cur` \
mapkey(continued) `igToolbar_AncestorIGT_IGT_GRP_inh407984315.proe_win:casc340798662`;\
mapkey(continued) ~ Close `main_dlg_cur` \
mapkey(continued) `igToolbar_AncestorIGT_IGT_GRP_inh407984315.proe_win:casc340798662`;\
mapkey(continued) ~ Command `ProCmdViewOrient` ;~ Input `orient` `NameVw_IP` `F`;\
mapkey(continued) ~ Input `orient` `NameVw_IP` `FL`;~ Input `orient` `NameVw_IP` `FLA`;\
mapkey(continued) ~ Input `orient` `NameVw_IP` `FLAT`;~ Update `orient` `NameVw_IP` `FLAT`;\
mapkey(continued) ~ Activate `orient` `NameVw_IP`;~ Activate `orient` `OkPB`;
mapkey iso @MAPKEY_LABELCreate ISO View;\
mapkey(continued) ~ Select `main_dlg_cur` \
mapkey(continued) `igToolbar_AncestorIGT_IGT_GRP_inh407984315.proe_win:casc340798662`;\
mapkey(continued) ~ Close `main_dlg_cur` \
mapkey(continued) `igToolbar_AncestorIGT_IGT_GRP_inh407984315.proe_win:casc340798662`;\
mapkey(continued) ~ Command `ProCmdViewOrient` ;~ Input `orient` `NameVw_IP` `i`;\
mapkey(continued) ~ Input `orient` `NameVw_IP` `is`;~ Input `orient` `NameVw_IP` `iso`;\
mapkey(continued) ~ Update `orient` `NameVw_IP` `iso`;~ Activate `orient` `NameVw_IP`;\
mapkey(continued) ~ Activate `orient` `OkPB`;
pro_format_dir C:\PTC_Data\formats
pro_material_dir C:\PTC_Data\Materials
nmgr_outdated_mp do_not_show
web_browser_homepage file:///C:/Program%20Files/PTC/Creo%2010.0.0.0/Common%20Files/apps/creojs/creojsweb/workspace.html
enable_punditas_browser_tab no
enable_3dmodelspace_browser_tab no
activate_window_automatically yes
mapkey apsf @MAPKEY_LABELApply Sheet Format;~ Command `ProCmdDwgPageSetup` ;\
mapkey(continued) ~ Arm `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats` 2 `0` `fmt`;\
mapkey(continued) ~ Open `pagesetup` `TblFormats_INPUT`;~ Close `pagesetup` `TblFormats_INPUT`;\
mapkey(continued) ~ Select `pagesetup` `TblFormats_INPUT` 1 `Browse...`;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `pb_favorites__FAV_9_`;\
mapkey(continued) ~ Select `file_open` `Ph_list.Filelist` 1 `formats`;\
mapkey(continued) ~ Activate `file_open` `Ph_list.Filelist` 1 `formats`;
mapkey op @MAPKEY_LABELOpen Part;~ Command `ProCmdModelOpen` ;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `Current Dir`;~ Open `file_open` `Type`;\
mapkey(continued) ~ Close `file_open` `Type`;~ Select `file_open` `Type` 1 `db_2`;
mapkey oa @MAPKEY_LABELOpen Assembly;~ Command `ProCmdModelOpen` ;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `Current Dir`;~ Open `file_open` `Type`;\
mapkey(continued) ~ Close `file_open` `Type`;~ Select `file_open` `Type` 1 `db_1`;
mapkey od @MAPKEY_LABELOpen Drawing;~ Command `ProCmdModelOpen` ;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `Current Dir`;~ Open `file_open` `Type`;\
mapkey(continued) ~ Close `file_open` `Type`;~ Select `file_open` `Type` 1 `db_4`;
mapkey oo @MAPKEY_LABELOpen Working Dir;~ Command `ProCmdModelOpen` ;\
mapkey(continued) ~ Trail `` `` `DLG_PREVIEW_POST` `file_open`;\
mapkey(continued) ~ Activate `file_open` `Current Dir`;~ Open `file_open` `Type`;\
mapkey(continued) ~ Close `file_open` `Type`;~ Select `file_open` `Type` 1 `filter_proe_files`;
mapkey expdf @MAPKEY_LABELExport PDF to Export Folder;\
mapkey(continued) ~ Select `main_dlg_cur` `appl_casc`;~ Close `main_dlg_cur` `appl_casc`;\
mapkey(continued) ~ Command `ProCmdModelSaveAs` ;~ Open `file_saveas` `type_option`;\
mapkey(continued) ~ Close `file_saveas` `type_option`;\
mapkey(continued) ~ Select `file_saveas` `type_option` 1 `db_617`;\
mapkey(continued) ~ Activate `file_saveas` `pb_favorites__FAV_14_`;\
mapkey(continued) ~ Activate `file_saveas` `OK`;~ Activate `UI Message Dialog` `ok`;\
mapkey(continued) ~ Select `intf_profile` `pdf_export.PDFMainTab` 1 `pdf_export.PDFContent`;\
mapkey(continued) ~ Select `intf_profile` `pdf_export.pdf_font_stroke` 1 `pdf_stroke_all`;\
mapkey(continued) ~ Open `intf_profile` `pdf_export.pdf_save_mode_menu`;\
mapkey(continued) ~ Close `intf_profile` `pdf_export.pdf_save_mode_menu`;\
mapkey(continued) ~ Activate `intf_profile` `OkPshBtn`;
mapkey exofa ~ Select `main_dlg_cur` `appl_casc`;\
mapkey(continued) ~ Close `main_dlg_cur` `appl_casc`;~ Command `ProCmdModelSaveAs` ;\
mapkey(continued) ~ Open `file_saveas` `type_option`;~ Close `file_saveas` `type_option`;\
mapkey(continued) ~ Select `file_saveas` `type_option` 1 `db_552`;\
mapkey(continued) ~ Activate `file_saveas` `pb_favorites__FAV_10_`;\
mapkey(continued) ~ Activate `file_saveas` `OK`;~ FocusOut `export_slice` `ChordHeightPanel`;\
mapkey(continued) ~ Activate `export_slice` `AllGroup`;\
mapkey(continued) ~ Select `main_dlg_cur` `PHTLeft.AssyTree` 1 `T3 3`;\
mapkey(continued) ~ Trail `MiniToolbar` `MiniToolbar` `UIT_TRANSLUCENT` `NEED_TO_CLOSE`;\
mapkey(continued) ~ Activate `export_slice` `OK`;~ Command `ProCmdViewRepaint`;
mapkey exofa @MAPKEY_LABELExport OBJ os Assembly;\
mapkey(continued) ~ Select `main_dlg_cur` `appl_casc`;~ Close `main_dlg_cur` `appl_casc`;\
mapkey(continued) ~ Command `ProCmdModelSaveAs` ;~ Open `file_saveas` `type_option`;\
mapkey(continued) ~ Close `file_saveas` `type_option`;\
mapkey(continued) ~ Select `file_saveas` `type_option` 1 `db_552`;\
mapkey(continued) ~ Activate `file_saveas` `pb_favorites__FAV_10_`;\
mapkey(continued) ~ Activate `file_saveas` `OK`;~ FocusOut `export_slice` `ChordHeightPanel`;\
mapkey(continued) ~ Activate `export_slice` `AllGroup`;\
mapkey(continued) ~ Select `main_dlg_cur` `PHTLeft.AssyTree` 1 `T3 3`;\
mapkey(continued) ~ Trail `MiniToolbar` `MiniToolbar` `UIT_TRANSLUCENT` `NEED_TO_CLOSE`;\
mapkey(continued) ~ Activate `export_slice` `OK`;~ Command `ProCmdViewRepaint`;
mapkey exofp @MAPKEY_LABELExport OBJ of Part;\
mapkey(continued) ~ Close `main_dlg_cur` `appl_casc`;~ Command `ProCmdModelSaveAs` ;\
mapkey(continued) ~ Activate `file_saveas` `pb_favorites__FAV_10_`;\
mapkey(continued) ~ Open `file_saveas` `type_option`;~ Close `file_saveas` `type_option`;\
mapkey(continued) ~ Select `file_saveas` `type_option` 1 `db_552`;\
mapkey(continued) ~ Activate `file_saveas` `pb_favorites__FAV_10_`;\
mapkey(continued) ~ Activate `file_saveas` `OK`;\
mapkey(continued) ~ Select `main_dlg_cur` `PHTLeft.AssyTree` 1 `T3 3`;\
mapkey(continued) ~ Trail `MiniToolbar` `MiniToolbar` `UIT_TRANSLUCENT` `NEED_TO_CLOSE`;\
mapkey(continued) ~ FocusOut `export_slice` `ChordHeightPanel`;~ Activate `export_slice` `OK`;\
mapkey(continued) ~ Command `ProCmdViewRepaint`;
mapkey exsta @MAPKEY_LABELExport STEP of Assembly;\
mapkey(continued) ~ Select `main_dlg_cur` `appl_casc`;~ Close `main_dlg_cur` `appl_casc`;\
mapkey(continued) ~ Command `ProCmdModelSaveAs` ;\
mapkey(continued) ~ Activate `file_saveas` `pb_favorites__FAV_10_`;\
mapkey(continued) ~ Open `file_saveas` `type_option`;~ Close `file_saveas` `type_option`;\
mapkey(continued) ~ Select `file_saveas` `type_option` 1 `db_539`;\
mapkey(continued) ~ Activate `file_saveas` `psh_export_opts`;\
mapkey(continued) ~ Open `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst`;\
mapkey(continued) ~ Close `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst`;\
mapkey(continued) ~ Select `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst` 1 \
mapkey(continued) `sep_parts`;~ Activate `dex_exp_profile_dialog` `CommitCancel`;\
mapkey(continued) ~ Activate `file_saveas` `psh_export_opts`;\
mapkey(continued) ~ Open `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst`;\
mapkey(continued) ~ Close `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst`;\
mapkey(continued) ~ Select `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst` 1 \
mapkey(continued) `single_file`;\
mapkey(continued) ~ Open `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst`;\
mapkey(continued) ~ Close `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst`;\
mapkey(continued) ~ Select `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst` 1 \
mapkey(continued) `sep_parts`;\
mapkey(continued) ~ Open `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst`;\
mapkey(continued) ~ Close `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst`;\
mapkey(continued) ~ Select `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst` 1 \
mapkey(continued) `single_file`;~ Activate `dex_exp_profile_dialog` `CommitOK`;\
mapkey(continued) ~ Activate `file_saveas` `psh_export_opts`;\
mapkey(continued) ~ Open `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst`;\
mapkey(continued) ~ Close `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst`;\
mapkey(continued) ~ Select `dex_exp_profile_dialog` `opts_ph.exp_asm_as_om.editor_inst` 1 \
mapkey(continued) `sep_parts`;~ Activate `dex_exp_profile_dialog` `CommitOK`;\
mapkey(continued) ~ Activate `file_saveas` `OK`;
mapkey exstp @MAPKEY_LABELExport STEP of Part;\
mapkey(continued) ~ Select `main_dlg_cur` `appl_casc`;~ Close `main_dlg_cur` `appl_casc`;\
mapkey(continued) ~ Command `ProCmdModelSaveAs` ;~ Open `file_saveas` `type_option`;\
mapkey(continued) ~ Close `file_saveas` `type_option`;\
mapkey(continued) ~ Select `file_saveas` `type_option` 1 `db_539`;\
mapkey(continued) ~ Activate `file_saveas` `pb_favorites__FAV_10_`;\
mapkey(continued) ~ Activate `file_saveas` `OK`;
