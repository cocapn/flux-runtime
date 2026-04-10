"""
Open-Flux-Interpreter — Markdown → Bytecode → Execution

The crown jewel: agents and users define vocabulary folders that map
natural language patterns to FLUX bytecode. Markdown becomes compute.

Usage:
    from flux.open_interp import OpenFluxInterpreter
    
    interp = OpenFluxInterpreter()
    interp.load_vocabulary("vocabularies/core")
    interp.load_vocabulary("vocabularies/math")
    
    result = interp.run("compute factorial of 7")
    print(result)  # 5040
"""
