# nsi-orchestrator

The NSI orchestrator maintains the lifecycle of network topologies, switching
services, Service Termination Points (STP), Service Demarcation Points (SDP),
and the Multi Domain Point-to-Point (MDP2P) services across a NSI
infrastructure, using the
[NSI DDS Proxy](https://github.com/workfloworchestrator/nsi-dds-proxy)
as source of information and the
[NSI Aggregator Proxy](https://github.com/workfloworchestrator/nsi-aggregator-proxy)
as its Network Resource Manager (NRM).

## Products and Product Blocks

```mermaid
%%{init: {"look": "handDrawn", "theme": "neutral"}}%%
classDiagram
    namespace MDP2P {
        class VirtualCircuitBlock {
            +description
            +saps
            +service_speed
            +sdp_constraints
        }
        class ServiceAttachmentPointBlock {
            +label
            +stp
        }
        class SdpConstraintBlock {
            +constraint_type
            +sdp
        }
    }
    namespace STP {
        class ServiceTerminationPointBlock {
            +stp_id
            +stp_name
            +capacity
            +label_group
            +switching_service
        }
    }
    namespace SDP {
        class ServiceDemarcationPointBlock {
            +sdp_name
            +stps
        }
    }
    namespace SwitchingService {
        class SwitchingServiceBlock {
            +switching_service_id
            +switching_service_name
            +topology
        }
    }
    namespace Topology {
        class TopologyBlock {
            +topology_id
            +topology_name
        }
    }

    VirtualCircuitBlock "1" -- "2" ServiceAttachmentPointBlock
    ServiceAttachmentPointBlock "n" -- "1" ServiceTerminationPointBlock
    ServiceTerminationPointBlock "n" -- "1" SwitchingServiceBlock
    SwitchingServiceBlock "n" -- "1" TopologyBlock
    VirtualCircuitBlock "n"  -- "n" SdpConstraintBlock
    SdpConstraintBlock "1"  -- "1" ServiceDemarcationPointBlock
    ServiceDemarcationPointBlock "1"  -- "2" ServiceTerminationPointBlock
```
