primary_plane: 2
reads_from: [3, 4]
writes_to: [2]
floor: 2
ceiling: 4
compilers:
  - name: deepseek-chat
    from: 4
    to: 2
    locks: 7
reasoning: |
  Flux-runtime is the FLUX VM bytecode interpreter executing at Plane 2.
  It provides the core virtual machine for interpreting FLUX bytecode (2) generated
  from Structured IR (3) or Domain Language (4). The ceiling at Plane 4 reflects
  that it's a technical component focused on bytecode execution, not natural language.

  As the VM layer, it reads typed JSON IR (3) and Domain Language notation (4) to
  compile into FLUX bytecode (2), then executes the bytecode with sandbox guarantees.
  This is the foundational execution engine that holodeck-studio and other Plane 2
  components rely on.
