"""
FundFlow AI — Unified Demo Runner

Runs the complete platform locally:
1. Generates synthetic transaction data
2. Starts the Risk Scoring API (port 8000)
3. Starts the Feedback Loop API (port 8001)
4. Sends a sample scoring request to demonstrate the system
5. Prints instructions for starting the Investigator Dashboard

Usage:
    python run_demo.py
"""

import subprocess
import sys
import time
import json
import os
import signal
import threading

# ─── Colors for terminal output ─────────────────────────────────────────────

class C:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    END = "\033[0m"


def banner():
    print(f"""
{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   ███████╗██╗   ██╗███╗   ██╗██████╗ ███████╗██╗      ██████╗   ║
║   ██╔════╝██║   ██║████╗  ██║██╔══██╗██╔════╝██║     ██╔═══██╗  ║
║   █████╗  ██║   ██║██╔██╗ ██║██║  ██║█████╗  ██║     ██║   ██║  ║
║   ██╔══╝  ██║   ██║██║╚██╗██║██║  ██║██╔══╝  ██║     ██║   ██║  ║
║   ██║     ╚██████╔╝██║ ╚████║██████╔╝██║     ███████╗╚██████╔╝  ║
║   ╚═╝      ╚═════╝ ╚═╝  ╚═══╝╚═════╝ ╚═╝     ╚══════╝ ╚═════╝  ║
║                                                                  ║
║     Intelligent Fund Flow Tracking & Suspicious Pattern          ║
║     Detection Platform — Demo Runner                             ║
╚══════════════════════════════════════════════════════════════════╝{C.END}
""")


def step(num, total, msg):
    print(f"\n{C.BOLD}{C.BLUE}[{num}/{total}]{C.END} {C.BOLD}{msg}{C.END}")


def success(msg):
    print(f"  {C.GREEN}✓{C.END} {msg}")


def info(msg):
    print(f"  {C.CYAN}ℹ{C.END} {msg}")


def warn(msg):
    print(f"  {C.YELLOW}⚠{C.END} {msg}")


def error(msg):
    print(f"  {C.RED}✗{C.END} {msg}")


def run_step_1_generate_data():
    """Generate synthetic transaction data."""
    step(1, 5, "Generating synthetic transaction data")

    output_dir = os.path.join("data-generator", "output")

    # Check if data already exists
    if (os.path.exists(os.path.join(output_dir, "accounts.json"))
            and os.path.exists(os.path.join(output_dir, "transactions.json"))):
        info("Data already exists in data-generator/output/")
        info("Delete the output folder to regenerate")

        # Print summary if it exists
        summary_path = os.path.join(output_dir, "summary.txt")
        if os.path.exists(summary_path):
            with open(summary_path, "r") as f:
                for line in f.readlines()[:10]:
                    print(f"    {line.rstrip()}")
        return True

    info("Generating 500 accounts, 30 days of transactions (small demo dataset)...")

    # Add data-generator to path so imports work
    sys.path.insert(0, "data-generator")
    try:
        from data_generator.generator import generate
        result = generate(
            num_accounts=500,
            days=30,
            seed=42,
            output_dir=output_dir,
            layering_count=20,
            round_trip_count=15,
            structuring_count=25,
            dormant_count=15,
            mismatch_count=25,
        )
        success(f"Generated {result['num_transactions']:,} transactions ({result['num_suspicious']:,} suspicious)")
        success(f"Ground truth: {result['num_patterns']} patterns across 5 typologies")
        return True
    except Exception as e:
        error(f"Data generation failed: {e}")
        return False


def run_step_2_score_sample():
    """Send a sample scoring request to demonstrate the risk engine."""
    step(2, 5, "Testing Risk Scoring Engine (in-process)")

    sys.path.insert(0, "risk-scoring")
    try:
        from risk_scoring.scorer import RiskScorer
        from risk_scoring.evidence import EvidenceGenerator

        scorer = RiskScorer()
        evidence_gen = EvidenceGenerator()

        # High-risk cluster
        model_probs = {
            "layering_gnn": 0.87,
            "round_tripping_xgb": 0.12,
            "structuring_iforest": 0.05,
            "dormant_activation_svm": 0.72,
            "profile_mismatch_lgbm": 0.65,
        }
        context = {"is_pep": False, "high_risk_jurisdiction": True, "rapid_pass_through": True}

        score, level = scorer.calculate_score(model_probs, context)
        narrative = evidence_gen.generate(model_probs, context, score)

        print(f"""
  {C.BOLD}═══════════════════════════════════════════════════{C.END}
  {C.BOLD}CLUSTER RISK ASSESSMENT — CLU-DEMO-001{C.END}
  {C.BOLD}═══════════════════════════════════════════════════{C.END}
  Overall Score: {C.RED if score >= 60 else C.YELLOW}{C.BOLD}{score}/100 ({level}){C.END}

  {C.BOLD}MODEL SIGNALS:{C.END}""")
        model_names = {
            "layering_gnn": "Layering (GraphSAGE)",
            "round_tripping_xgb": "Round-Tripping (XGBoost)",
            "structuring_iforest": "Structuring (IForest)",
            "dormant_activation_svm": "Dormant Activation (SVM)",
            "profile_mismatch_lgbm": "Profile Mismatch (LGBM)",
        }
        for model, prob in model_probs.items():
            bar_len = int(prob * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            color = C.RED if prob > 0.7 else C.YELLOW if prob > 0.4 else C.GREEN
            print(f"    {model_names[model]:<30} {color}{bar} {prob*100:.0f}%{C.END}")

        print(f"\n  {C.BOLD}EVIDENCE NARRATIVE:{C.END}")
        for line in narrative:
            print(f"    {line}")
        print(f"  {C.BOLD}═══════════════════════════════════════════════════{C.END}")

        success(f"Risk score computed: {score}/100 ({level})")
        return True
    except Exception as e:
        error(f"Risk scoring failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_step_3_test_feedback():
    """Test the feedback loop module."""
    step(3, 5, "Testing Feedback Loop Engine (in-process)")

    sys.path.insert(0, "feedback")
    try:
        from feedback_core import DispositionRecorder, FPDampeningModel, PSIMonitor
        import tempfile
        from pathlib import Path

        # Use a temp file so we don't pollute the project
        import feedback.feedback_core as fc
        tmp = tempfile.mktemp(suffix=".json")
        fc.STORAGE_PATH = Path(tmp)

        recorder = DispositionRecorder()

        # Record some sample dispositions
        recorder.record("CLU-DEMO-001", "INV-001", "TRUE_POSITIVE",
                        feature_vector={"risk_score": 87, "layering_gnn": 0.87})
        recorder.record("CLU-DEMO-002", "INV-001", "FALSE_POSITIVE",
                        reason_code="NORMAL_BUSINESS",
                        feature_vector={"risk_score": 35, "layering_gnn": 0.12})
        recorder.record("CLU-DEMO-003", "INV-002", "ESCALATED")

        stats = recorder.get_stats()
        success(f"Recorded 3 dispositions: {stats['true_positives']} TP, "
                f"{stats['false_positives']} FP, {stats['pending']} Pending")
        info(f"Retrain needed: {'Yes' if stats['retrain_needed'] else 'No'} "
             f"({stats['tp_since_retrain']}/{stats['retrain_threshold']} TPs)")

        # Clean up temp file
        try:
            Path(tmp).unlink()
        except Exception:
            pass

        return True
    except Exception as e:
        error(f"Feedback loop test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def start_api_server(name, module, port, cwd=None):
    """Start a FastAPI server in a background process."""
    env = os.environ.copy()
    if cwd:
        env["PYTHONPATH"] = cwd + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [
        sys.executable, "-m", "uvicorn",
        module, "--host", "127.0.0.1", "--port", str(port),
        "--log-level", "warning"
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd or ".",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
        )
        time.sleep(2)
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            error(f"{name} failed to start: {stderr[:200]}")
            return None
        success(f"{name} running at http://127.0.0.1:{port}")
        return proc
    except Exception as e:
        error(f"Failed to start {name}: {e}")
        return None


def run_step_4_start_apis():
    """Start the Risk Scoring and Feedback APIs."""
    step(4, 5, "Starting API servers")

    procs = []

    # Start Risk Scoring API
    info("Starting Risk Scoring API on port 8000...")
    p1 = start_api_server("Risk Scoring API", "risk_scoring.api:app", 8000, cwd="risk-scoring")
    if p1:
        procs.append(p1)

    # Start Feedback API
    info("Starting Feedback Loop API on port 8001...")
    p2 = start_api_server("Feedback Loop API", "feedback.api:app", 8001, cwd="feedback")
    if p2:
        procs.append(p2)

    if procs:
        # Quick health check
        time.sleep(1)
        try:
            import urllib.request
            resp = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3)
            if resp.status == 200:
                success("Risk Scoring API health check passed")
        except Exception:
            warn("Risk Scoring API health check failed (may still be starting)")

        try:
            import urllib.request
            resp = urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=3)
            if resp.status == 200:
                success("Feedback Loop API health check passed")
        except Exception:
            warn("Feedback Loop API health check failed (may still be starting)")

    return procs


def run_step_5_instructions():
    """Print instructions for running the dashboard."""
    step(5, 5, "Dashboard & Next Steps")

    print(f"""
  {C.BOLD}{C.CYAN}┌──────────────────────────────────────────────────────────────┐
  │                  PLATFORM IS RUNNING!                       │
  └──────────────────────────────────────────────────────────────┘{C.END}

  {C.BOLD}APIs Running:{C.END}
    • Risk Scoring API:   {C.GREEN}http://127.0.0.1:8000{C.END}  ({C.CYAN}http://127.0.0.1:8000/docs{C.END} for Swagger UI)
    • Feedback Loop API:  {C.GREEN}http://127.0.0.1:8001{C.END}  ({C.CYAN}http://127.0.0.1:8001/docs{C.END} for Swagger UI)

  {C.BOLD}Start the Investigator Dashboard:{C.END}
    Open a new terminal and run:
    {C.YELLOW}cd dashboard/dashboard && npm run dev{C.END}
    Then open {C.GREEN}http://localhost:3000{C.END} in your browser.

  {C.BOLD}What you can do:{C.END}
    1. {C.CYAN}Investigator Dashboard{C.END} — View alerts, explore fund flow graphs,
       click on account nodes, generate evidence packages, file STRs
    2. {C.CYAN}Risk Scoring API{C.END} — POST to /api/v1/score with model probabilities
    3. {C.CYAN}Feedback API{C.END} — Record investigator dispositions, train FP model
    4. {C.CYAN}Generate more data{C.END} — cd data-generator && python -m data_generator.generator --accounts 5000 --days 60

  {C.BOLD}Other commands:{C.END}
    • Run all tests:  {C.YELLOW}pytest data-generator/tests/ -v{C.END}
    • Run risk tests:  {C.YELLOW}cd risk-scoring && pytest tests/ -v{C.END}
    • Run feedback tests:  {C.YELLOW}cd feedback && pytest test_feedback.py -v{C.END}

  {C.BOLD}Press Ctrl+C to stop all servers.{C.END}
""")


def main():
    banner()

    # Step 1: Generate data
    run_step_1_generate_data()

    # Step 2: Test risk scoring
    run_step_2_score_sample()

    # Step 3: Test feedback
    run_step_3_test_feedback()

    # Step 4: Start APIs
    procs = run_step_4_start_apis()

    # Step 5: Instructions
    run_step_5_instructions()

    if procs:
        try:
            print(f"  {C.CYAN}Servers are running. Press Ctrl+C to stop.{C.END}\n")
            while True:
                time.sleep(1)
                # Check if any process has died
                for p in procs:
                    if p.poll() is not None:
                        warn(f"A server process exited (PID {p.pid})")
        except KeyboardInterrupt:
            print(f"\n  {C.YELLOW}Shutting down servers...{C.END}")
            for p in procs:
                try:
                    p.terminate()
                    p.wait(timeout=5)
                except Exception:
                    p.kill()
            success("All servers stopped.")
    else:
        warn("No API servers were started. You can still use the components individually.")


if __name__ == "__main__":
    main()
