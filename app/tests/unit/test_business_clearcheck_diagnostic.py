"""Generic output/template contracts, without model-quality labels."""
import importlib.util
from pathlib import Path
import sys

SCRIPTS=Path(__file__).resolve().parents[3]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('clearcheck',SCRIPTS/'compare_business_clearcheck.py')
cc=importlib.util.module_from_spec(spec);spec.loader.exec_module(cc)
sys.path.remove(str(SCRIPTS))


def test_three_way_labels_are_separate_and_missing_conclusion_unresolved():
    assert cc.label_from_raw('[Extraction] passage\n[Conclusion] [Not Attributable]')=='Not Attributable'
    assert cc.label_from_raw('[Inference] passage\n[Contradictory]')=='Contradictory'
    assert cc.label_from_raw('[Attributable]')=='Attributable'
    assert cc.label_from_raw('[Extraction] passage') is None
    assert cc.label_from_raw('Attributable') is None


def test_upstream_template_is_read_without_executing_package(tmp_path):
    source=tmp_path/'templates.py'
    source.write_text('raise RuntimeError("must not execute")\nDOCUMENT_PLACEHOLDER="DOC"\nSTATEMENT_PLACEHOLDER="CLAIM"\nCLEARCHECK_COT=f"{DOCUMENT_PLACEHOLDER} then {STATEMENT_PLACEHOLDER}"\n')
    template,names=cc.official_template(source)
    assert template=='DOC then CLAIM'
    assert names==dict(DOCUMENT_PLACEHOLDER='DOC',STATEMENT_PLACEHOLDER='CLAIM')
