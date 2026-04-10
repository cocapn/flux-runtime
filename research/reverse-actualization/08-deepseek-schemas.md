```json
[
  {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Vulnerability Report",
    "description": "I2I (Infrastructure-to-Infrastructure) protocol weakness report for FLUX ecosystem",
    "type": "object",
    "required": [
      "reportId",
      "timestamp",
      "severity",
      "affectedComponents",
      "weaknessType",
      "description"
    ],
    "properties": {
      "reportId": {
        "type": "string",
        "format": "uuid",
        "description": "Unique identifier for the vulnerability report"
      },
      "timestamp": {
        "type": "string",
        "format": "date-time",
        "description": "ISO 8601 timestamp of when the vulnerability was reported"
      },
      "reporter": {
        "type": "string",
        "description": "Entity or node that identified the vulnerability",
        "maxLength": 256
      },
      "severity": {
        "type": "string",
        "enum": ["critical", "high", "medium", "low", "informational"],
        "description": "Impact assessment of the vulnerability"
      },
      "affectedComponents": {
        "type": "array",
        "items": {
          "type": "string"
        },
        "description": "List of FLUX protocol components or modules affected",
        "minItems": 1
      },
      "weaknessType": {
        "type": "string",
        "description": "Classification of the protocol weakness",
        "examples": ["authentication-bypass", "data-integrity", "resource-exhaustion", "timing-attack"]
      },
      "description": {
        "type": "string",
        "description": "Detailed explanation of the vulnerability"
      },
      "proofOfConcept": {
        "type": "object",
        "description": "Optional demonstration of exploitability",
        "properties": {
          "method": {
            "type": "string"
          },
          "successProbability": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
          }
        }
      },
      "mitigationStatus": {
        "type": "string",
        "enum": ["pending", "in-progress", "patched", "wont-fix"],
        "description": "Current remediation status"
      }
    },
    "example": {
      "reportId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "timestamp": "2024-01-15T14:30:00Z",
      "reporter": "flux-node-7a32",
      "severity": "high",
      "affectedComponents": ["cross-chain-validator", "consensus-engine"],
      "weaknessType": "timing-attack",
      "description": "Side-channel vulnerability in cross-chain validation allows inference of private validation keys through timing analysis",
      "proofOfConcept": {
        "method": "Differential timing analysis with 10k samples",
        "successProbability": 0.85
      },
      "mitigationStatus": "in-progress"
    }
  },
  {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Ghost Advisory",
    "description": "Ghost vessel detection and advisory records with temporal confidence scoring",
    "type": "object",
    "required": [
      "advisoryId",
      "detectionTime",
      "vesselSignature",
      "confidence",
      "threatLevel",
      "temporalValidity"
    ],
    "properties": {
      "advisoryId": {
        "type": "string",
        "format": "uuid",
        "description": "Unique identifier for the ghost advisory"
      },
      "detectionTime": {
        "type": "string",
        "format": "date-time",
        "description": "When the ghost vessel was first detected"
      },
      "lastSeen": {
        "type": "string",
        "format": "date-time",
        "description": "Most recent observation timestamp"
      },
      "vesselSignature": {
        "type": "string",
        "description": "Pattern or hash identifying the ghost vessel behavior",
        "pattern": "^[a-fA-F0-9]{64}$"
      },
      "behaviorType": {
        "type": "string",
        "enum": ["replay-attempt", "identity-spoof", "consensus-disruptor", "data-siphon", "unknown"],
        "description": "Classification of observed ghost behavior"
      },
      "confidence": {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
        "description": "Detection confidence score (0 to 1)"
      },
      "threatLevel": {
        "type": "string",
        "enum": ["benign", "low", "medium", "high", "critical"],
        "description": "Assessed threat to FLUX ecosystem"
      },
      "temporalValidity": {
        "type": "object",
        "description": "Time-based confidence and expiration",
        "required": ["start", "confidenceDecayRate"],
        "properties": {
          "start": {
            "type": "string",
            "format": "date-time"
          },
          "end": {
            "type": "string",
            "format": "date-time"
          },
          "confidenceDecayRate": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Rate at which confidence decreases per hour"
          }
        }
      },
      "affectedZones": {
        "type": "array",
        "items": {
          "type": "string"
        },
        "description": "FLUX network zones where vessel was observed"
      },
      "countermeasures": {
        "type": "array",
        "items": {
          "type": "string"
        },
        "description": "Recommended mitigation actions"
      }
    },
    "example": {
      "advisoryId": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
      "detectionTime": "2024-01-15T22:45:00Z",
      "lastSeen": "2024-01-15T23:10:00Z",
      "vesselSignature": "a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef",
      "behaviorType": "consensus-disruptor",
      "confidence": 0.92,
      "threatLevel": "high",
      "temporalValidity": {
        "start": "2024-01-15T22:45:00Z",
        "end": "2024-01-16T06:00:00Z",
        "confidenceDecayRate": 0.1
      },
      "affectedZones": ["alpha-sector", "gamma-cluster"],
      "countermeasures": ["increase-validator-quorum", "enable-signature-rotation"]
    }
  },
  {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Emergence Report",
    "description": "Documentation of emergent behaviors from FLUX system interactions",
    "type": "object",
    "required": [
      "reportId",
      "observationStart",
      "emergentBehavior",
      "triggeringComponents",
      "stabilityRating",
      "impactAssessment"
    ],
    "properties": {
      "reportId": {
        "type": "string",
        "format": "uuid",
        "description": "Unique identifier for the emergence report"
      },
      "observationStart": {
        "type": "string",
        "format": "date-time",
        "description": "When the emergent behavior was first observed"
      },
      "observationDuration": {
        "type": "number",
        "minimum": 0,
        "description": "Duration of observation in seconds"
      },
      "emergentBehavior": {
        "type": "string",
        "description": "Description of the unexpected system behavior"
      },
      "triggeringComponents": {
        "type": "array",
        "items": {
          "type": "string"
        },
        "description": "System components whose interaction caused emergence",
        "minItems": 2
      },
      "interactionPattern": {
        "type": "string",
        "description": "Pattern of component interaction leading to emergence",
        "examples": ["feedback-loop", "cascading-failure", "synergistic-enhancement", "phase-transition"]
      },
      "stabilityRating": {
        "type": "string",
        "enum": ["stable", "meta-stable", "unstable", "chaotic"],
        "description": "Stability assessment of the emergent behavior"
      },
      "impactAssessment": {
        "type": "object",
        "required": ["systemImpact", "recommendedAction"],
        "properties": {
          "systemImpact": {
            "type": "string",
            "enum": ["positive", "neutral", "negative", "catastrophic"]
          },
          "performanceChange": {
            "type": "number",
            "description": "Percentage change in system performance metrics"
          },
          "recommendedAction": {
            "type": "string",
            "enum": ["amplify", "maintain", "mitigate", "eliminate"]
          }
        }
      },
      "reproducibilityScore": {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
        "description": "Likelihood of behavior recurring under same conditions"
      },
      "dataArtifacts": {
        "type": "array",
        "items": {
          "type": "string",
          "format": "uri"
        },
        "description": "Links to telemetry or diagnostic data capturing the event"
      }
    },
    "example": {
      "reportId": "c3d4e5f6-a7b8-9012-cdef-345678901234",
      "observationStart": "2024-01-15T18:20:00Z",
      "observationDuration": 3600,
      "emergentBehavior": "Non-linear throughput scaling when cross-chain validators synchronize with oracle feeds, resulting in 300% efficiency gain beyond component specifications",
      "triggeringComponents": ["quantum-oracle-v3", "cross-chain-bridge", "adaptive-load-balancer"],
      "interactionPattern": "synergistic-enhancement",
      "stabilityRating": "meta-stable",
      "impactAssessment": {
        "systemImpact": "positive",
        "performanceChange": 300,
        "recommendedAction": "amplify"
      },
      "reproducibilityScore": 0.75,
      "dataArtifacts": [
        "flux://telemetry/emergent/2024-01-15T18:20:00Z/logs",
        "flux://metrics/throughput/anomaly-7b32"
      ]
    }
  }
]
```
