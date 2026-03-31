import os
import shutil
import time
import logging
from state import OptimizerState
from utils.file_ops import write_to_file

logger = logging.getLogger("opc.archive")

def archive_node(state: OptimizerState) -> OptimizerState:
    logger.info("--- 🗂️ ARCHIVE PHASE ---")
    current_round = state.get("current_round", 1)
    project_path = state["project_path"]
    
    archive_every_n = state.get("archive_every_n_rounds", 3)
    
    if current_round % archive_every_n == 0:
        logger.info(f"Round {current_round} triggers archiving (every {archive_every_n} rounds).")
        log_dir = os.path.join(project_path, ".opclog")
        archive_dir = os.path.join(project_path, ".opclog", "archive", f"round_{current_round}_{int(time.time())}")
        
        os.makedirs(archive_dir, exist_ok=True)
        
        files_to_archive = ["plan.md", "suggestions.md", "CHANGELOG.md"]
        
        for file in files_to_archive:
            src = os.path.join(log_dir, file)
            dst = os.path.join(archive_dir, file)
            if os.path.exists(src):
                # Copy current to archive
                shutil.copy2(src, dst)
                # Clear active files to prevent context swelling
                # Note: Do NOT clear suggestions.md here — it's needed by the next round's plan node
                if file == "plan.md":
                    write_to_file(src, "")
                elif file == "CHANGELOG.md":
                    # For changelog we just write a rollup marker
                    write_to_file(src, f"# CHANGELOG Tracker\n\n*Previous {current_round} rounds archived in {archive_dir}*\n\n")
        
        logger.info(f"Archived historical data to: {archive_dir}")
        
        # Clean up .bak files from execute node
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', 'venv', '__pycache__', '.opclog'}]
            for f in files:
                if f.endswith('.bak'):
                    bak_path = os.path.join(root, f)
                    try:
                        os.remove(bak_path)
                        logger.info(f"  Cleaned up: {bak_path}")
                    except OSError:
                        pass
        
    else:
        logger.info(f"Round {current_round} is not a multiple of {archive_every_n}. Skipping archiving.")
        
    return state
