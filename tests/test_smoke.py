import pmc


def test_package_version():
    assert pmc.__version__ == "0.1.0"


def test_imports():
    from pmc.memory import PMCMemory
    from pmc.planner import Plan, Step, generate_plan, validate_plan
    from pmc.executor import Executor
    from pmc.verifier import verify
    from pmc.synthesis import synthesize
    from pmc.ingestion import ingest_filesystem
    from pmc.dataset import generate_pairs, split_pairs
    assert all([PMCMemory, Plan, Step, generate_plan, validate_plan,
                Executor, verify, synthesize, ingest_filesystem,
                generate_pairs, split_pairs])
