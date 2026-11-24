import sys
import time
sys.path.append("src")

import config
from utils import warm_up
from stage1_requirements import generate_requirements
from stage2_sdlc import choose_sdlc
from make_report import build_report

if __name__ == "__main__":
    if len(sys.argv) > 1:
        config.FUNCTIONALITY = " ".join(sys.argv[1:])
    else:
        typed = input(f"Enter the functionality (Enter for default: '{config.FUNCTIONALITY}'): ").strip()
        if typed:
            config.FUNCTIONALITY = typed

    print(f"\nFunctionality: {config.FUNCTIONALITY}\n")
    t0 = time.time()
    warm_up()
    print(f"Model ready in {time.time() - t0:.1f}s\n")

    t1 = time.time()
    requirements = generate_requirements()   # Part 1
    t2 = time.time()
    choose_sdlc(requirements)                # Part 2: derived only from the requirements
    t3 = time.time()
    build_report(config.FUNCTIONALITY, config.MODEL)

    print(f"\nTiming: Stage 1 = {t2 - t1:.0f}s, Stage 2 = {t3 - t2:.0f}s, total = {time.time() - t0:.0f}s")
    print("Done! Check the outputs/ folder.")