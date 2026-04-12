#!/usr/bin/env python3
"""
domain_classifier.py - Fleet Knowledge Domain Classifier

Classifies any text/file into FLUX fleet knowledge domains using
keyword-based classification with confidence scoring. No ML dependencies.

Supports 20+ knowledge domains specific to the FLUX fleet including
bytecode_vm, cuda, fleet_protocol, security, testing, networking,
compilers, runtimes, observability, and more.

Usage:
    from domain_classifier import DomainClassifier

    clf = DomainClassifier()
    results = clf.classify_file("path/to/file.rs")
    results = clf.classify_text("This implements a CUDA kernel for matrix multiply...")
    results = clf.bulk_classify(file_paths=["a.py", "b.rs", "c.cu"])
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Knowledge Domain Definitions
# ---------------------------------------------------------------------------

class DomainCategory(Enum):
    """High-level grouping of knowledge domains."""
    SYSTEMS = "systems"
    SOFTWARE = "software"
    INFRASTRUCTURE = "infrastructure"
    SECURITY = "security"
    RESEARCH = "research"
    OPERATIONS = "operations"


@dataclass(frozen=True)
class KnowledgeDomain:
    """A single knowledge domain with keywords, patterns, and metadata."""
    name: str
    display_name: str
    description: str
    keywords: Tuple[str, ...]
    patterns: Tuple[str, ...]  # regex patterns
    file_extensions: Tuple[str, ...]
    category: DomainCategory
    related_domains: Tuple[str, ...] = ()
    weight: float = 1.0  # multiplier for confidence scoring


# ---------------------------------------------------------------------------
# Fleet-Specific Domain Taxonomy (20+ domains)
# ---------------------------------------------------------------------------

FLEET_DOMAINS: Dict[str, KnowledgeDomain] = {
    "bytecode_vm": KnowledgeDomain(
        name="bytecode_vm",
        display_name="Bytecode VM",
        description="Virtual machines, bytecode interpreters, instruction sets, "
                    "stack machines, register machines, JIT compilation",
        keywords=(
            "bytecode", "virtual machine", "vm", "interpreter", "opcode",
            "instruction set", "stack machine", "register machine", "execution engine",
            "disassembler", "assembler", "code generation", "ir", "intermediate representation",
            "compilation pipeline", "parse tree", "ast", "abstract syntax",
        ),
        patterns=(
            r"\bopcodes?\b", r"\bbytecode\b", r"\bvirtual[_ ]machine\b",
            r"\bstack[-_]machine\b", r"\bregister[-_]machine\b",
            r"\binterpret(er|ation)\b", r"\bdisassembl", r"\bjit\b",
            r"\bexecution[-_]engine\b", r"\binstruction[-_]set\b",
        ),
        file_extensions=(".bc", ".class", ".wasm", ".beam",),
        category=DomainCategory.SYSTEMS,
        related_domains=("compilers", "runtimes", "cuda"),
        weight=1.2,
    ),

    "cuda": KnowledgeDomain(
        name="cuda",
        display_name="CUDA / GPU Computing",
        description="CUDA programming, GPU kernels, CUDA runtime, "
                    "compute shaders, parallel computing on GPUs",
        keywords=(
            "cuda", "gpu", "kernel", "cudaMemcpy", "cudaMalloc", "cublas",
            "cufft", "cudnn", "tensor core", "warp", "thread block",
            "shared memory", "global memory", "stream", "event",
            "nvcc", ".cu", "ptx", "sass", "cubin",
            "compute capability", "sm_", "grid stride", "cooperative groups",
            "tensor operation", "matrix multiply", "sgemm", "gemm",
        ),
        patterns=(
            r"\bcuda\b", r"\b__global__\b", r"\b__device__\b",
            r"\b__host__\b", r"\b__shared__\b", r"\b__constant__\b",
            r"\bcudaMemcpy\b", r"\bcudaMalloc\b", r"\bcudaLaunchKernel\b",
            r"\bgridDim\b", r"\bblockDim\b", r"\bthreadIdx\b", r"\bblockIdx\b",
            r"\bsm_\d+\b", r"\bcublas\b", r"\bcufft\b", r"\bcudnn\b",
            r"\bnvcc\b", r"\b\.cu\b",
        ),
        file_extensions=(".cu", ".cuh", ".ptx",),
        category=DomainCategory.SYSTEMS,
        related_domains=("bytecode_vm", "compilers", "runtimes"),
        weight=1.3,
    ),

    "compilers": KnowledgeDomain(
        name="compilers",
        display_name="Compilers & Language Design",
        description="Compiler construction, lexing, parsing, optimization passes, "
                    "code generation, type systems, language design",
        keywords=(
            "compiler", "lexer", "parser", "syntax", "semantic analysis",
            "optimization", "code generation", "type system", "type checker",
            "llvm", "llvm ir", "pass manager", "ssa", "control flow graph",
            "data flow analysis", "dead code elimination", "inlining",
            "loop optimization", "register allocation", "instruction selection",
            "target triple", "backend", "frontend",
        ),
        patterns=(
            r"\bcompil(er|ation)\b", r"\bparse[rt]\b", r"\blex(er|ing)\b",
            r"\bllvm\b", r"\bssa\b", r"\boptimiz(ation|er|e)\b",
            r"\btype[-_]?check", r"\bcontrol[-_]flow\b", r"\bdata[-_]flow\b",
            r"\bregister[-_]allocat", r"\bdead[-_]code\b", r"\binlining\b",
            r"\bloop[-_]optim", r"\bIR[-_]?builder\b",
        ),
        file_extensions=(".ll", ".mir",),
        category=DomainCategory.SYSTEMS,
        related_domains=("bytecode_vm", "runtimes"),
        weight=1.1,
    ),

    "runtimes": KnowledgeDomain(
        name="runtimes",
        display_name="Runtime Systems",
        description="Language runtimes, garbage collection, memory management, "
                    "runtime linking, dynamic loading, sandboxing",
        keywords=(
            "runtime", "garbage collector", "gc", "memory allocator", "mmap",
            "linker", "dynamic loading", "dlOpen", "dlopen", "jit compiler",
            "sandbox", "capability-based security", "wasm runtime",
            "stack unwinding", "exception handling", "signal handler",
            "runtime library", "startup code", "crt",
        ),
        patterns=(
            r"\bruntime\b", r"\bgarbage[-_]collect", r"\bgc\b",
            r"\bmemory[-_]allocat", r"\bdlopen\b", r"\bdl(sym|close)\b",
            r"\bsandbox\b", r"\bstack[-_]unwind", r"\bsignal[-_]?handler\b",
        ),
        file_extensions=(),
        category=DomainCategory.SYSTEMS,
        related_domains=("bytecode_vm", "compilers", "security"),
        weight=1.0,
    ),

    "fleet_protocol": KnowledgeDomain(
        name="fleet_protocol",
        display_name="Fleet Protocol & Orchestration",
        description="Fleet communication protocols, agent orchestration, "
                    "distributed coordination, fleet management, task dispatch",
        keywords=(
            "fleet", "agent", "orchestration", "dispatch", "task queue",
            "worker pool", "coordinator", "heartbeat", "leader election",
            "distributed lock", "consensus", "raft", "paxos",
            "message broker", "pubsub", "rpc", "grpc",
            "superinstance", "lucineer", "oracle",
            "bottle", "flux-runtime", "fleet-context",
            "capability profile", "agent registry",
        ),
        patterns=(
            r"\bfleet\b", r"\borchestration\b", r"\bdispatch\b",
            r"\bcoordinator\b", r"\bheartbeat\b", r"\bleader[-_]elect",
            r"\bconsensus\b", r"\braft\b", r"\bpaxos\b",
            r"\bsuperinstance\b", r"\blucineer\b", r"\boracle\b",
            r"\bflux[-_]runtime\b", r"\bfleet[-_]context\b",
            r"\bagent[-_]?regist",
        ),
        file_extensions=(),
        category=DomainCategory.INFRASTRUCTURE,
        related_domains=("networking", "observability"),
        weight=1.4,
    ),

    "networking": KnowledgeDomain(
        name="networking",
        display_name="Networking & Protocols",
        description="Network protocols, sockets, HTTP, TCP/UDP, websockets, "
                    "DNS, load balancing, proxy, CDN",
        keywords=(
            "tcp", "udp", "http", "https", "websocket", "socket",
            "tls", "ssl", "dns", "dhcp", "nat", "firewall",
            "load balancer", "proxy", "reverse proxy", "cdn",
            "packet", "frame", "mtu", "backlog", "listen",
            "connection pool", "keepalive", "retry", "circuit breaker",
        ),
        patterns=(
            r"\btcp\b", r"\budp\b", r"\bhttps?\b", r"\bwebsocket\b",
            r"\bsocket\b", r"\btls\b", r"\bssl\b", r"\bdns\b",
            r"\bload[-_]balanc", r"\bproxy\b", r"\bcdn\b",
            r"\bpacket\b", r"\bconnection[-_]pool\b",
        ),
        file_extensions=(),
        category=DomainCategory.INFRASTRUCTURE,
        related_domains=("fleet_protocol", "security"),
        weight=0.9,
    ),

    "security": KnowledgeDomain(
        name="security",
        display_name="Security & Cryptography",
        description="Cryptography, authentication, authorization, "
                    "vulnerability scanning, secure coding, threat modeling",
        keywords=(
            "cryptograph", "encrypt", "decrypt", "hash", "sha256", "sha512",
            "aes", "rsa", "ecdsa", "hmac", "signature", "certificate",
            "tls", "ssl", "oauth", "jwt", "token", "api key",
            "vulnerability", "exploit", "sandbox", "seccomp", "selinux",
            "capability", "permission", "role-based", "rbac",
            "audit log", "security policy", "threat model",
            "supply chain", "dependency scan", "sast", "dast",
        ),
        patterns=(
            r"\bencrypt(ion|ed|s)?\b", r"\bdecrypt(ion|ed|s)?\b",
            r"\bsha256\b", r"\bsha512\b", r"\baes\b", r"\brsa\b",
            r"\becdsa\b", r"\bhmac\b", r"\boauth\b", r"\bjwt\b",
            r"\bvulnerabilit", r"\bexploit\b", r"\bsandbox\b",
            r"\bseccomp\b", r"\bselinux\b", r"\brbac\b",
            r"\bthreat[-_]model\b", r"\bsecurity[-_]policy\b",
        ),
        file_extensions=(),
        category=DomainCategory.SECURITY,
        related_domains=("fleet_protocol", "networking"),
        weight=1.2,
    ),

    "testing": KnowledgeDomain(
        name="testing",
        display_name="Testing & Quality Assurance",
        description="Unit testing, integration testing, property testing, "
                    "fuzzing, code coverage, test frameworks, TDD",
        keywords=(
            "test", "unit test", "integration test", "e2e test",
            "property test", "fuzz test", "fuzzer", "mutation test",
            "coverage", "code coverage", "assert", "expect", "mock",
            "stub", "fixture", "snapshot", "benchmark", "criterion",
            "proptest", "quickcheck", "hypothesis", "pytest",
            "cargo test", "jest", "mocha", "vitest",
            "regression", "smoke test", "contract test",
        ),
        patterns=(
            r"\bunit[-_]test\b", r"\bintegration[-_]test\b",
            r"\btest[-_]suite\b", r"\btest[-_]case\b",
            r"\bfuzz(ing|er)?\b", r"\bproptest\b", r"\bquickcheck\b",
            r"\bcoverage\b", r"\bsnapshot[-_]test\b",
            r"\b#\[test\]\b", r"\b#\[cfg\(test\)\]\b",  # Rust
            r"\b@pytest\b", r"\bdef test_\b",               # Python
            r"\bdescribe\s*\(", r"\bit\s*\(\s*['\"]",       # JS
        ),
        file_extensions=(),
        category=DomainCategory.SOFTWARE,
        related_domains=("observability", "devops"),
        weight=0.8,
    ),

    "observability": KnowledgeDomain(
        name="observability",
        display_name="Observability & Monitoring",
        description="Logging, metrics, tracing, alerting, dashboards, "
                    "distributed tracing, OpenTelemetry, Prometheus",
        keywords=(
            "log", "metric", "trace", "span", "alert", "dashboard",
            "prometheus", "grafana", "opentelemetry", "otel",
            "jaeger", "zipkin", "datadog", "new relic",
            "structured logging", "log level", "error rate",
            "latency histogram", "slo", "sli", "error budget",
            "health check", "readiness", "liveness", "probe",
        ),
        patterns=(
            r"\bopentelemetry\b", r"\bopentelemetry\b", r"\bprometheus\b",
            r"\bgrafana\b", r"\bjaeger\b", r"\bdashboard\b",
            r"\bSLO\b", r"\bSLI\b", r"\berror[-_]budget\b",
            r"\bhealth[-_]check\b", r"\breadiness\b", r"\bliveness\b",
        ),
        file_extensions=(),
        category=DomainCategory.OPERATIONS,
        related_domains=("devops", "testing"),
        weight=0.9,
    ),

    "devops": KnowledgeDomain(
        name="devops",
        display_name="DevOps & CI/CD",
        description="Continuous integration, continuous deployment, "
                    "containerization, infrastructure as code, GitOps",
        keywords=(
            "ci", "cd", "cicd", "pipeline", "github actions", "jenkins",
            "docker", "container", "kubernetes", "k8s", "helm",
            "terraform", "ansible", "puppet", "cloudformation",
            "gitops", "argo", "flux", "deploy", "rollback",
            "blue-green", "canary", "feature flag",
            "infrastructure as code", "iac",
        ),
        patterns=(
            r"\bgithub[-_]?actions\b", r"\bjenkins\b", r"\bdocker\b",
            r"\bkubernetes\b", r"\bk8s\b", r"\bterraform\b",
            r"\bCI[-_/]?CD\b", r"\bpipeline\b", r"\bdeploy(ment|s)?\b",
            r"\bhelm\b", r"\bargo(cd)?\b",
        ),
        file_extensions=(".dockerfile", ".tf", ".hcl",),
        category=DomainCategory.OPERATIONS,
        related_domains=("observability", "testing"),
        weight=0.8,
    ),

    "ml_ai": KnowledgeDomain(
        name="ml_ai",
        display_name="Machine Learning & AI",
        description="Machine learning, deep learning, neural networks, "
                    "model training, inference, NLP, computer vision",
        keywords=(
            "machine learning", "deep learning", "neural network",
            "model training", "inference", "prediction", "classification",
            "regression", "clustering", "transformer", "attention",
            "encoder", "decoder", "embedding", "vector database",
            "pytorch", "tensorflow", "onnx", "tensorrt",
            "llm", "large language model", "gpt", "bert",
            "fine-tuning", "rlhf", "prompt engineering",
            "diffusion", "stable diffusion", "gan",
        ),
        patterns=(
            r"\bmachine[-_]learning\b", r"\bdeep[-_]learning\b",
            r"\bneural[-_]network\b", r"\binference\b",
            r"\btransformer\b", r"\battemption\b",
            r"\bpytorch\b", r"\btensorflow\b", r"\bonnx\b",
            r"\bllm\b", r"\blarge[-_]language[-_]model\b",
            r"\bR[Ll]HF\b", r"\bfine[-_]tun",
        ),
        file_extensions=(".onnx", ".pt", ".pth", ".safetensors",),
        category=DomainCategory.RESEARCH,
        related_domains=("cuda", "data_processing"),
        weight=1.1,
    ),

    "data_processing": KnowledgeDomain(
        name="data_processing",
        display_name="Data Processing & ETL",
        description="Data pipelines, ETL, stream processing, batch processing, "
                    "data formats, serialization, databases",
        keywords=(
            "etl", "data pipeline", "stream processing", "batch processing",
            "apache kafka", "rabbitmq", "redis", "sqlite", "postgresql",
            "dataframe", "polars", "pandas", "arrow",
            "parquet", "avro", "protobuf", "json", "csv",
            "deserialization", "serialization", "schema",
            "data lake", "data warehouse", "olap", "oltp",
        ),
        patterns=(
            r"\betl\b", r"\bdata[-_]pipeline\b", r"\bstream[-_]process",
            r"\bbatch[-_]process", r"\bdataframe\b",
            r"\bparquet\b", r"\bavro\b", r"\bprotobuf\b",
            r"\bpostgresql\b", r"\bsqlite\b",
        ),
        file_extensions=(".parquet", ".avro",),
        category=DomainCategory.SOFTWARE,
        related_domains=("ml_ai", "observability"),
        weight=0.9,
    ),

    "web_development": KnowledgeDomain(
        name="web_development",
        display_name="Web Development",
        description="Frontend and backend web development, REST APIs, "
                    "web frameworks, single-page applications",
        keywords=(
            "rest api", "graphql", "frontend", "backend",
            "react", "vue", "angular", "svelte", "next.js", "nuxt",
            "express", "fastapi", "django", "flask", "actix", "axum",
            "html", "css", "javascript", "typescript", "webassembly",
            "spa", "ssr", "hydration", "component",
            "endpoint", "middleware", "router", "handler",
        ),
        patterns=(
            r"\breact\b", r"\bvue\b", r"\bangular\b", r"\bsvelte\b",
            r"\bnext\.?js\b", r"\bexpress\b", r"\bfastapi\b",
            r"\bdjango\b", r"\bgraphql\b", r"\bwebassembly\b",
            r"\brest[-_]?api\b",
        ),
        file_extensions=(".jsx", ".tsx", ".vue", ".svelte",),
        category=DomainCategory.SOFTWARE,
        related_domains=("networking", "devops"),
        weight=0.8,
    ),

    "systems_programming": KnowledgeDomain(
        name="systems_programming",
        display_name="Systems Programming",
        description="Low-level systems programming, OS internals, "
                    "concurrency, memory management, kernel development",
        keywords=(
            "kernel", "driver", "syscall", "interrupt", "page fault",
            "memory mapping", "virtual memory", "concurrency", "mutex",
            "semaphore", "atomic", "lock-free", "wait-free",
            "thread", "async", "await", "future", "coroutine",
            "io_uring", "epoll", "kqueue", "eventfd",
            "zero-copy", "memory barrier", "cache line",
        ),
        patterns=(
            r"\bsyscall\b", r"\binterrupt\b", r"\bpage[-_]fault\b",
            r"\bvirtual[-_]memory\b", r"\bmutex\b", r"\bsemaphore\b",
            r"\batomic\b", r"\block[-_]free\b", r"\bio_uring\b",
            r"\bepoll\b", r"\beventfd\b", r"\bzero[-_]copy\b",
            r"\bmemory[-_]barrier\b", r"\bcache[-_]line\b",
        ),
        file_extensions=(),
        category=DomainCategory.SYSTEMS,
        related_domains=("runtimes", "cuda", "bytecode_vm"),
        weight=1.0,
    ),

    "formal_methods": KnowledgeDomain(
        name="formal_methods",
        display_name="Formal Methods & Verification",
        description="Formal verification, model checking, theorem proving, "
                    "correctness proofs, specification languages",
        keywords=(
            "formal verification", "model checking", "theorem prover",
            "proof assistant", "tla+", "alloy", "coq", "lean",
            "smt solver", "z3", "sat solver", "linear temporal logic",
            "safety property", "liveness property", "invariant",
            "precondition", "postcondition", "hoare logic",
            "correctness proof", "refinement",
        ),
        patterns=(
            r"\bformal[-_]verif\b", r"\bmodel[-_]check", r"\btheorem[-_]prov",
            r"\bproof[-_]assist", r"\btla\+\b", r"\bcoq\b",
            r"\bsmt[-_]?solver\b", r"\bz3\b", r"\bsat[-_]?solver\b",
            r"\bcorrectness[-_]proof\b",
        ),
        file_extensions=(),
        category=DomainCategory.RESEARCH,
        related_domains=("testing", "security"),
        weight=1.3,
    ),

    "database": KnowledgeDomain(
        name="database",
        display_name="Database Systems",
        description="Database internals, query engines, storage engines, "
                    "indexing, transaction processing, distributed databases",
        keywords=(
            "query engine", "storage engine", "b-tree", "lsm tree",
            "index", "transaction", "acid", "mvcc",
            "query planner", "query optimizer", "join", "aggregate",
            "columnar", "row-oriented", "write-ahead log", "wal",
            "replication", "sharding", "partitioning", "consistency",
            "sqlite", "postgres", "mysql", "mongodb", "redis",
        ),
        patterns=(
            r"\bquery[-_]engine\b", r"\bstorage[-_]engine\b",
            r"\blsm[-_]tree\b", r"\bb[-_]?tree\b", r"\bmvcc\b",
            r"\bwrite[-_]ahead[-_]log\b", r"\bwal\b",
            r"\bcolumnar\b", r"\breplication\b", r"\bshard",
        ),
        file_extensions=(".sql",),
        category=DomainCategory.SYSTEMS,
        related_domains=("data_processing", "devops"),
        weight=0.9,
    ),

    "distributed_systems": KnowledgeDomain(
        name="distributed_systems",
        display_name="Distributed Systems",
        description="Distributed algorithms, consensus, replication, "
                    "partition tolerance, consistency models, CAP theorem",
        keywords=(
            "distributed", "consensus", "replication", "partition",
            "cap theorem", "byzantine", "fault tolerance",
            "eventual consistency", "strong consistency", "linearizability",
            "crdt", "vector clock", "lamport clock", "logical clock",
            "gossip protocol", "anti-entropy", "merge conflict",
            "quorum", "split brain", "network partition",
        ),
        patterns=(
            r"\bdistributed\b", r"\bbyzantine\b", r"\bfault[-_]toleran",
            r"\beventual[-_]consist", r"\blinearizab", r"\bcrdt\b",
            r"\bvector[-_]clock\b", r"\bgossip[-_]protocol\b",
            r"\banti[-_]entropy\b", r"\bnetwork[-_]partition\b",
        ),
        file_extensions=(),
        category=DomainCategory.INFRASTRUCTURE,
        related_domains=("fleet_protocol", "database", "networking"),
        weight=1.1,
    ),

    "cli_tools": KnowledgeDomain(
        name="cli_tools",
        display_name="CLI Tools & Utilities",
        description="Command-line tools, argument parsing, shell scripting, "
                    "terminal UI, text processing utilities",
        keywords=(
            "cli", "command line", "argument parser", "subcommand",
            "terminal", "tui", "text ui", "ncurses", "crossterm",
            "shell script", "bash", "zsh", "pipe", "redirect",
            "text processing", "sed", "awk", "grep", "regex",
            "color output", "progress bar", "spinner",
            "interactive prompt", "readline", "completion",
        ),
        patterns=(
            r"\bcommand[-_]line\b", r"\bargument[-_]pars",
            r"\bsubcommand\b", r"\bterminal\b", r"\bncurses\b",
            r"\bcrossterm\b", r"\btext[-_]process",
        ),
        file_extensions=(".sh", ".bash", ".zsh",),
        category=DomainCategory.SOFTWARE,
        related_domains=("devops", "web_development"),
        weight=0.7,
    ),

    "api_design": KnowledgeDomain(
        name="api_design",
        display_name="API Design & Documentation",
        description="REST API design, OpenAPI, GraphQL schema design, "
                    "versioning, error handling, rate limiting",
        keywords=(
            "openapi", "swagger", "api specification", "endpoint design",
            "rate limiting", "throttling", "circuit breaker",
            "api versioning", "backward compatibility", "deprecation",
            "error code", "status code", "pagination",
            "graphql schema", "resolver", "subscription",
            "webhook", "callback", "sdk", "client library",
        ),
        patterns=(
            r"\bopenapi\b", r"\bswagger\b", r"\bapi[-_]specif",
            r"\brate[-_]limit", r"\bapi[-_]version",
            r"\bgraphql[-_]?schema\b", r"\bwebhook\b",
            r"\bbackward[-_]compat",
        ),
        file_extensions=(".graphql", ".gql",),
        category=DomainCategory.SOFTWARE,
        related_domains=("web_development", "fleet_protocol"),
        weight=0.8,
    ),

    "embedded": KnowledgeDomain(
        name="embedded",
        display_name="Embedded & IoT",
        description="Embedded systems, microcontrollers, firmware, "
                    "real-time systems, hardware interfaces",
        keywords=(
            "embedded", "microcontroller", "firmware", "bare metal",
            "real-time", "rtos", "freeRTOS", "interrupt handler",
            "gpio", "i2c", "spi", "uart", "dma",
            "memory-mapped", "hardware register", "bit manipulation",
            "bootloader", "flash memory", "watchdog timer",
        ),
        patterns=(
            r"\bembedded\b", r"\bmicrocontroller\b", r"\bfirmware\b",
            r"\bbare[-_]metal\b", r"\brtos\b", r"\bfreeRTOS\b",
            r"\bgpio\b", r"\bmemory[-_]mapped\b",
        ),
        file_extensions=(".ino", ".hex", ".bin",),
        category=DomainCategory.SYSTEMS,
        related_domains=("systems_programming", "security"),
        weight=0.9,
    ),

    "documentation": KnowledgeDomain(
        name="documentation",
        display_name="Documentation & Knowledge Management",
        description="Technical writing, documentation tools, knowledge bases, "
                    "specifications, architecture decision records",
        keywords=(
            "readme", "documentation", "docs", "tutorial", "guide",
            "architecture decision record", "adr", "design doc",
            "specification", "rfc", "proposal", "knowledge base",
            "wiki", "confluence", "notion", "markdown",
            "javadoc", "rustdoc", "pydoc", "docstring",
            "code comment", "inline documentation",
        ),
        patterns=(
            r"\breadme\b", r"\bdocumentation\b", r"\barchitectur(ure|al)",
            r"\badr\b", r"\bdesign[-_]doc\b", r"\brfc\b",
            r"\brustdoc\b", r"\bjavadoc\b", r"\bpydoc\b",
        ),
        file_extensions=(".md", ".rst", ".adoc", ".txt",),
        category=DomainCategory.SOFTWARE,
        related_domains=("api_design", "devops"),
        weight=0.6,
    ),

    "build_systems": KnowledgeDomain(
        name="build_systems",
        display_name="Build Systems & Package Management",
        description="Build tools, package managers, dependency management, "
                    "artifact repositories, reproducible builds",
        keywords=(
            "cargo", "npm", "pip", "maven", "gradle", "makefile",
            "cmake", "bazel", "buck", "nix", "guix",
            "package manager", "dependency", "lock file",
            "artifact", "repository", "registry",
            "reproducible build", "hermetic build", "sandbox build",
            "cache", "build cache", "remote execution",
            "monorepo", "workspace", "feature flag",
        ),
        patterns=(
            r"\bcargo\.(toml|lock)\b", r"\bpackage\.json\b",
            r"\brequirements\.txt\b", r"\bCMakeLists\.txt\b",
            r"\bMakefile\b", r"\bBUILD\b",  # Bazel
            r"\breproducible[-_]build\b", r"\bhermetic[-_]build\b",
            r"\bmonorepo\b",
        ),
        file_extensions=(".toml",),
        category=DomainCategory.INFRASTRUCTURE,
        related_domains=("devops", "security"),
        weight=0.8,
    ),

    "cryptography": KnowledgeDomain(
        name="cryptography",
        display_name="Advanced Cryptography",
        description="Cryptographic protocols, zero-knowledge proofs, "
                    "homomorphic encryption, post-quantum crypto",
        keywords=(
            "zero-knowledge proof", "zkp", "zk-SNARK", "zk-STARK",
            "homomorphic encryption", "fhe",
            "post-quantum", "lattice-based", "kyber", "dilithium",
            "elliptic curve", "secp256k1", "ed25519",
            "merkle tree", "verifiable random function", "vrf",
            "threshold signature", "multi-party computation", "mpc",
            "commitment scheme", "bulletproof",
        ),
        patterns=(
            r"\bzero[-_]knowledge\b", r"\bzk[-_]SNARK\b", r"\bzk[-_]STARK\b",
            r"\bhomomorphic\b", r"\bfhe\b",
            r"\bpost[-_]quantum\b", r"\blattice[-_]based\b",
            r"\bmerkle[-_]tree\b", r"\bvrf\b", r"\bmpc\b",
            r"\bthreshold[-_]signat",
        ),
        file_extensions=(),
        category=DomainCategory.SECURITY,
        related_domains=("security", "formal_methods"),
        weight=1.4,
    ),
}


# ---------------------------------------------------------------------------
# Classification Result
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    """Result of classifying a text into knowledge domains."""
    text_hash: str
    text_length: int
    domain_scores: Dict[str, float] = field(default_factory=dict)
    primary_domain: Optional[str] = None
    secondary_domains: List[str] = field(default_factory=list)
    keyword_matches: Dict[str, List[str]] = field(default_factory=dict)
    pattern_matches: Dict[str, List[str]] = field(default_factory=dict)
    extension_matches: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_classified(self) -> bool:
        return self.primary_domain is not None

    def top_domains(self, n: int = 5) -> List[Tuple[str, float]]:
        """Return top N domains by score, sorted descending."""
        return sorted(self.domain_scores.items(), key=lambda x: x[1], reverse=True)[:n]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text_hash": self.text_hash,
            "text_length": self.text_length,
            "domain_scores": self.domain_scores,
            "primary_domain": self.primary_domain,
            "secondary_domains": self.secondary_domains,
            "keyword_matches": self.keyword_matches,
            "pattern_matches": self.pattern_matches,
            "extension_matches": self.extension_matches,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClassificationResult":
        return cls(
            text_hash=data["text_hash"],
            text_length=data["text_length"],
            domain_scores=data.get("domain_scores", {}),
            primary_domain=data.get("primary_domain"),
            secondary_domains=data.get("secondary_domains", []),
            keyword_matches=data.get("keyword_matches", {}),
            pattern_matches=data.get("pattern_matches", {}),
            extension_matches=data.get("extension_matches", []),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Domain Classifier
# ---------------------------------------------------------------------------

class DomainClassifier:
    """
    Keyword-based knowledge domain classifier for FLUX fleet repos.

    Classifies text into 20+ knowledge domains using a combination of:
    - Keyword matching with TF-aware scoring
    - Regex pattern matching for domain-specific idioms
    - File extension hints
    - Domain weighting and confidence calibration

    No external ML dependencies required.
    """

    def __init__(
        self,
        domains: Optional[Dict[str, KnowledgeDomain]] = None,
        min_confidence: float = 0.05,
        keyword_boost: float = 1.0,
        pattern_boost: float = 1.5,
        extension_boost: float = 2.0,
        max_domains: int = 10,
    ):
        """
        Initialize the classifier.

        Args:
            domains: Override the default domain definitions.
            min_confidence: Minimum confidence score to include a domain.
            keyword_boost: Score multiplier for keyword matches.
            pattern_boost: Score multiplier for regex pattern matches.
            extension_boost: Score multiplier for file extension matches.
            max_domains: Maximum number of domains to return.
        """
        self.domains = domains or FLEET_DOMAINS
        self.min_confidence = min_confidence
        self.keyword_boost = keyword_boost
        self.pattern_boost = pattern_boost
        self.extension_boost = extension_boost
        self.max_domains = max_domains

        # Pre-compile regex patterns for performance
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}
        for domain_name, domain in self.domains.items():
            compiled = []
            for pattern in domain.patterns:
                try:
                    compiled.append(re.compile(pattern, re.IGNORECASE))
                except re.error:
                    pass  # skip invalid patterns
            self._compiled_patterns[domain_name] = compiled

        # Pre-build keyword lookup for fast matching
        self._keyword_index: Dict[str, List[Tuple[str, KnowledgeDomain]]] = {}
        for domain_name, domain in self.domains.items():
            for keyword in domain.keywords:
                keyword_lower = keyword.lower()
                if keyword_lower not in self._keyword_index:
                    self._keyword_index[keyword_lower] = []
                self._keyword_index[keyword_lower].append((domain_name, domain))

    def classify_text(
        self,
        text: str,
        filename: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ClassificationResult:
        """
        Classify a text string into knowledge domains.

        Args:
            text: The text to classify.
            filename: Optional filename for extension-based hints.
            metadata: Optional metadata to attach to the result.

        Returns:
            ClassificationResult with domain scores and matches.
        """
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        text_length = len(text)
        text_lower = text.lower()

        domain_scores: Dict[str, float] = {}
        keyword_matches: Dict[str, List[str]] = defaultdict(list)
        pattern_matches: Dict[str, List[str]] = defaultdict(list)
        extension_matches: List[str] = []

        # --- Phase 1: Keyword matching ---
        keyword_counts = Counter()
        for word in re.findall(r"[a-zA-Z_][\w.-]*", text_lower):
            keyword_counts[word] += 1

        total_keywords_found = 0
        for keyword_lower, domain_list in self._keyword_index.items():
            # Check if this keyword appears in the text
            if keyword_lower in keyword_counts:
                count = keyword_counts[keyword_lower]
                total_keywords_found += count
                for domain_name, domain in domain_list:
                    keyword_matches[domain_name].append(keyword_lower)
                    # Score: count * domain_weight * keyword_boost
                    domain_scores[domain_name] = (
                        domain_scores.get(domain_name, 0.0)
                        + count * domain.weight * self.keyword_boost
                    )

        # Also check multi-word keywords
        for domain_name, domain in self.domains.items():
            for keyword in domain.keywords:
                if " " in keyword or "-" in keyword:
                    kw_lower = keyword.lower()
                    occurrences = text_lower.count(kw_lower)
                    if occurrences > 0:
                        keyword_matches[domain_name].append(kw_lower)
                        total_keywords_found += occurrences
                        domain_scores[domain_name] = (
                            domain_scores.get(domain_name, 0.0)
                            + occurrences * domain.weight * self.keyword_boost
                        )

        # --- Phase 2: Pattern matching ---
        for domain_name, patterns in self._compiled_patterns.items():
            domain = self.domains[domain_name]
            for pattern in patterns:
                matches = pattern.findall(text)
                if matches:
                    match_count = len(matches)
                    match_str = pattern.pattern[:50]
                    pattern_matches[domain_name].append(match_str)
                    domain_scores[domain_name] = (
                        domain_scores.get(domain_name, 0.0)
                        + match_count * domain.weight * self.pattern_boost
                    )

        # --- Phase 3: File extension matching ---
        if filename:
            _, ext = os.path.splitext(filename.lower())
            if ext:
                for domain_name, domain in self.domains.items():
                    if ext in domain.file_extensions:
                        extension_matches.append(domain_name)
                        domain_scores[domain_name] = (
                            domain_scores.get(domain_name, 0.0)
                            + domain.weight * self.extension_boost
                        )

        # --- Phase 4: Normalize scores ---
        if domain_scores:
            max_score = max(domain_scores.values())
            if max_score > 0:
                # Normalize to 0-1 range and apply min_confidence filter
                normalized = {}
                for domain_name, score in domain_scores.items():
                    norm_score = score / max_score
                    if norm_score >= self.min_confidence:
                        normalized[domain_name] = round(norm_score, 4)
                domain_scores = normalized

        # --- Phase 5: Determine primary and secondary domains ---
        primary_domain = None
        secondary_domains = []

        if domain_scores:
            sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
            primary_domain = sorted_domains[0][0]

            # Secondary domains: those with >= 50% of primary score
            primary_score = sorted_domains[0][1]
            for domain_name, score in sorted_domains[1 : self.max_domains]:
                if score >= primary_score * 0.5:
                    secondary_domains.append(domain_name)

            # Include related domains of primary if they have any score
            if primary_domain in self.domains:
                primary_rel = self.domains[primary_domain].related_domains
                for rel in primary_rel:
                    if rel in domain_scores and rel not in secondary_domains:
                        if domain_scores[rel] >= primary_score * 0.3:
                            secondary_domains.append(rel)

        result = ClassificationResult(
            text_hash=text_hash,
            text_length=text_length,
            domain_scores=domain_scores,
            primary_domain=primary_domain,
            secondary_domains=secondary_domains,
            keyword_matches=dict(keyword_matches),
            pattern_matches=dict(pattern_matches),
            extension_matches=extension_matches,
            metadata=metadata or {},
        )

        return result

    def classify_file(self, file_path: str) -> ClassificationResult:
        """
        Classify a file by reading its content.

        Args:
            file_path: Path to the file to classify.

        Returns:
            ClassificationResult for the file.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Try to read with UTF-8, fall back to latin-1
        try:
            content = path.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1", errors="replace")

        metadata = {
            "file_path": str(path),
            "file_size": path.stat().st_size,
            "file_extension": path.suffix,
            "file_name": path.name,
        }

        return self.classify_text(content, filename=path.name, metadata=metadata)

    def bulk_classify(
        self,
        file_paths: List[str],
        max_workers: int = 4,
        show_progress: bool = True,
    ) -> Dict[str, ClassificationResult]:
        """
        Classify multiple files in parallel.

        Args:
            file_paths: List of file paths to classify.
            max_workers: Number of parallel workers.
            show_progress: Whether to print progress.

        Returns:
            Dict mapping file paths to ClassificationResults.
        """
        results: Dict[str, ClassificationResult] = {}

        try:
            from concurrent.futures import ProcessPoolExecutor, as_completed

            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                future_to_path = {
                    executor.submit(self._classify_file_safe, fp): fp
                    for fp in file_paths
                }
                completed = 0
                total = len(file_paths)
                for future in as_completed(future_to_path):
                    fp = future_to_path[future]
                    try:
                        result = future.result()
                        if result is not None:
                            results[fp] = result
                    except Exception:
                        pass  # skip files that fail
                    completed += 1
                    if show_progress and completed % 50 == 0:
                        print(f"  Classified {completed}/{total} files...")
        except ImportError:
            # Fall back to sequential processing
            for i, fp in enumerate(file_paths):
                try:
                    results[fp] = self.classify_file(fp)
                except Exception:
                    pass
                if show_progress and (i + 1) % 50 == 0:
                    print(f"  Classified {i + 1}/{len(file_paths)} files...")

        if show_progress:
            print(f"  Classification complete: {len(results)}/{len(file_paths)} files classified.")

        return results

    def _classify_file_safe(self, file_path: str) -> Optional[ClassificationResult]:
        """Safe wrapper for parallel file classification."""
        try:
            return self.classify_file(file_path)
        except Exception:
            return None

    def classify_directory(
        self,
        dir_path: str,
        extensions: Optional[List[str]] = None,
        max_files: int = 1000,
        max_workers: int = 4,
    ) -> Dict[str, ClassificationResult]:
        """
        Classify all files in a directory tree.

        Args:
            dir_path: Root directory to scan.
            extensions: Optional list of extensions to filter (e.g., [".rs", ".py"]).
            max_files: Maximum number of files to classify.
            max_workers: Number of parallel workers.

        Returns:
            Dict mapping file paths to ClassificationResults.
        """
        path = Path(dir_path)
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")

        # Collect files
        file_paths: List[str] = []
        ext_set = set(extensions) if extensions else None

        # Skip common non-knowledge directories
        skip_dirs = {
            ".git", "node_modules", "target", "build", "__pycache__",
            ".next", ".cache", "vendor", "third_party", "third-party",
            "dist", ".tox", ".mypy_cache", ".pytest_cache",
        }

        for root, dirs, files in os.walk(dir_path):
            # Prune skipped directories
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for fname in files:
                if ext_set:
                    _, ext = os.path.splitext(fname.lower())
                    if ext not in ext_set:
                        continue
                fpath = os.path.join(root, fname)
                if os.path.isfile(fpath):
                    file_paths.append(fpath)
                    if len(file_paths) >= max_files:
                        break
            if len(file_paths) >= max_files:
                break

        return self.bulk_classify(file_paths, max_workers=max_workers)

    def get_domain_summary(
        self, results: Dict[str, ClassificationResult]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Aggregate classification results into domain-level statistics.

        Args:
            results: Dict of file_path -> ClassificationResult.

        Returns:
            Domain summary with counts, average scores, and representative files.
        """
        domain_stats: Dict[str, Dict[str, Any]] = {}

        for file_path, result in results.items():
            for domain_name, score in result.domain_scores.items():
                if domain_name not in domain_stats:
                    domain_stats[domain_name] = {
                        "count": 0,
                        "total_score": 0.0,
                        "max_score": 0.0,
                        "files": [],
                        "primary_count": 0,
                    }
                stats = domain_stats[domain_name]
                stats["count"] += 1
                stats["total_score"] += score
                stats["max_score"] = max(stats["max_score"], score)
                stats["files"].append({
                    "path": file_path,
                    "score": score,
                })
                if result.primary_domain == domain_name:
                    stats["primary_count"] += 1

        # Compute averages and sort files by score
        for domain_name, stats in domain_stats.items():
            stats["avg_score"] = round(stats["total_score"] / stats["count"], 4)
            stats["files"].sort(key=lambda x: x["score"], reverse=True)
            # Keep only top 20 representative files
            stats["top_files"] = stats["files"][:20]
            del stats["files"]
            del stats["total_score"]

        return dict(sorted(domain_stats.items(), key=lambda x: x[1]["count"], reverse=True))

    def suggest_domains_for_query(self, query: str) -> List[Tuple[str, float]]:
        """
        Suggest which knowledge domains a search query might relate to.
        Useful for pre-filtering searches.

        Args:
            query: A search query string.

        Returns:
            List of (domain_name, score) tuples sorted by relevance.
        """
        result = self.classify_text(query)
        return result.top_domains(n=5)

    def list_domains(self) -> List[Dict[str, str]]:
        """
        List all available knowledge domains with metadata.

        Returns:
            List of domain info dicts.
        """
        return [
            {
                "name": domain.name,
                "display_name": domain.display_name,
                "description": domain.description,
                "category": domain.category.value,
                "related": list(domain.related_domains),
                "keyword_count": len(domain.keywords),
                "pattern_count": len(domain.patterns),
            }
            for domain in self.domains.values()
        ]


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for the domain classifier."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fleet Knowledge Domain Classifier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s classify "This implements a CUDA kernel for matrix multiply"
  %(prog)s classify-file path/to/file.rs
  %(prog)s scan-directory /path/to/repo --extensions .rs,.py
  %(prog)s list-domains
  %(prog)s suggest "how does the fleet handle agent dispatch?"
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # classify command
    classify_parser = subparsers.add_parser("classify", help="Classify a text string")
    classify_parser.add_argument("text", help="Text to classify")
    classify_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # classify-file command
    classify_file_parser = subparsers.add_parser("classify-file", help="Classify a file")
    classify_file_parser.add_argument("file", help="File path to classify")
    classify_file_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # scan-directory command
    scan_parser = subparsers.add_parser("scan-directory", help="Scan a directory")
    scan_parser.add_argument("directory", help="Directory to scan")
    scan_parser.add_argument(
        "--extensions", default=None,
        help="Comma-separated extensions (e.g., .rs,.py)",
    )
    scan_parser.add_argument("--max-files", type=int, default=500, help="Max files to scan")
    scan_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # list-domains command
    subparsers.add_parser("list-domains", help="List all knowledge domains")

    # suggest command
    suggest_parser = subparsers.add_parser("suggest", help="Suggest domains for a query")
    suggest_parser.add_argument("query", help="Search query")

    args = parser.parse_args()

    if args.command == "classify":
        clf = DomainClassifier()
        result = clf.classify_text(args.text)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"Primary domain: {result.primary_domain}")
            print(f"Secondary domains: {', '.join(result.secondary_domains)}")
            print(f"\nDomain scores:")
            for domain, score in result.top_domains(5):
                print(f"  {domain}: {score:.4f}")

    elif args.command == "classify-file":
        clf = DomainClassifier()
        result = clf.classify_file(args.file)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"File: {args.file}")
            print(f"Primary domain: {result.primary_domain}")
            print(f"Secondary domains: {', '.join(result.secondary_domains)}")
            print(f"\nDomain scores:")
            for domain, score in result.top_domains(5):
                print(f"  {domain}: {score:.4f}")

    elif args.command == "scan-directory":
        clf = DomainClassifier()
        extensions = args.extensions.split(",") if args.extensions else None
        results = clf.classify_directory(args.directory, extensions=extensions, max_files=args.max_files)
        summary = clf.get_domain_summary(results)
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"Scanned {len(results)} files, found {len(summary)} domains:\n")
            for domain_name, stats in summary.items():
                print(f"  {domain_name}: {stats['count']} files "
                      f"(avg score: {stats['avg_score']:.4f}, "
                      f"primary: {stats['primary_count']})")

    elif args.command == "list-domains":
        clf = DomainClassifier()
        domains = clf.list_domains()
        print(f"Available knowledge domains ({len(domains)}):\n")
        for d in domains:
            print(f"  {d['name']}: {d['display_name']}")
            print(f"    Category: {d['category']}")
            print(f"    {d['description'][:100]}")
            print(f"    Keywords: {d['keyword_count']}, Patterns: {d['pattern_count']}")
            print()

    elif args.command == "suggest":
        clf = DomainClassifier()
        suggestions = clf.suggest_domains_for_query(args.query)
        print(f"Suggested domains for: '{args.query}'\n")
        for domain, score in suggestions:
            domain_info = clf.domains[domain]
            print(f"  {domain}: {score:.4f} - {domain_info.display_name}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
