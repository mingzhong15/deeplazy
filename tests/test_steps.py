"""Smoke tests for step class attributes and registry."""
from dlazy.steps import create_step, _registry
from dlazy.steps.base import Step
from dlazy.steps.olp import OLPStep
from dlazy.steps.scf import SCFStep, SCFRestartStep
from dlazy.steps.infer import DeepHStep


def test_step_registry_has_all_types():
    assert "olp" in _registry
    assert "deeph" in _registry
    assert "scf" in _registry
    assert "scf-restart" in _registry


def test_all_steps_inherit_step_abc():
    assert issubclass(OLPStep, Step)
    assert issubclass(DeepHStep, Step)
    assert issubclass(SCFStep, Step)
    assert issubclass(SCFRestartStep, Step)


def test_step_runner_modes_declared():
    assert OLPStep.runner_mode == "parallel"
    assert SCFStep.runner_mode == "serial"
    assert SCFRestartStep.runner_mode == "serial"
    assert DeepHStep.runner_mode == "single"


def test_step_produces_dataset_flags():
    assert OLPStep.produces_dataset is False
    assert SCFStep.produces_dataset is True
    assert SCFRestartStep.produces_dataset is True
    assert DeepHStep.produces_dataset is False


def test_step_type_alias():
    step = SCFStep({"name": "e6", "type": "scf"},
                   {"work_dir": "/tmp", "steps": []}, {}, {})
    assert step.type_alias() == "fp"

    step = OLPStep({"name": "olp", "type": "olp"},
                   {"work_dir": "/tmp", "steps": []}, {}, {})
    assert step.type_alias() == "olp"


def test_create_step_instantiates_subclass():
    step = create_step({"name": "olp", "type": "olp"},
                       {"work_dir": "/tmp", "steps": []}, {}, {})
    assert isinstance(step, OLPStep)
    assert step.name == "olp"


def test_create_step_rejects_unknown_type():
    import pytest
    with pytest.raises(ValueError, match="Unknown step type"):
        create_step({"name": "x", "type": "bogus"}, {}, {}, {})


def test_step_is_massive_default_false():
    step = create_step({"name": "olp", "type": "olp"},
                       {"work_dir": "/tmp", "steps": []}, {}, {})
    assert step._is_massive() is False


def test_step_is_massive_true_when_param_mode_massive():
    step = create_step({"name": "olp", "type": "olp"},
                       {"work_dir": "/tmp", "mode": "massive", "steps": []}, {}, {})
    assert step._is_massive() is True
