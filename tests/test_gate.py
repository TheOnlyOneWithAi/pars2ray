from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]/'master'))
from app.services.gate import evaluate_gate

def test_keep_without_ai():
    r=evaluate_gate(93.9,94.1,False,False,False)
    assert r.call_ai is False and r.action=='KEEP'

def test_anomaly_calls_ai():
    r=evaluate_gate(80,94,True,False,False)
    assert r.call_ai is True
