# Copyright 2026 SURF.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Subscription description service.

A single ``description()`` generic function builds the human-readable description for a domain
model, dispatching on its (Provisioning) type. Register one implementation per product type here;
the registration for a ``*Provisioning`` model also covers its ``ACTIVE`` subclass via the MRO.
"""

from functools import singledispatch

from orchestrator.core.domain.base import (
    ProductBlockModel,
    ProductModel,
    SubscriptionModel,
)

from products.product_types.mdp2p import MultiDomainPoint2PointProvisioning
from products.product_types.sdp import ServiceDemarcationPointProvisioning
from products.product_types.stp import ServiceTerminationPointProvisioning
from products.product_types.switchingservice import SwitchingServiceProvisioning
from products.product_types.topology import TopologyProvisioning


@singledispatch
def description(model: ProductModel | ProductBlockModel | SubscriptionModel) -> str:
    """Build the description for a domain model; register a per-type implementation below."""
    raise TypeError(f"description() is not implemented for {type(model).__name__}")


@description.register
def _topology_description(topology: TopologyProvisioning) -> str:
    return f"{topology.product.tag} {topology.topology.topology_name}"


@description.register
def _switchingservice_description(
    switchingservice: SwitchingServiceProvisioning,
) -> str:
    return f"{switchingservice.product.tag} {switchingservice.switchingservice.switching_service_name}"


@description.register
def _stp_description(stp: ServiceTerminationPointProvisioning) -> str:
    return f"{stp.product.tag} {stp.stp.stp_name}"


@description.register
def _sdp_description(sdp: ServiceDemarcationPointProvisioning) -> str:
    return f"{sdp.product.tag} {sdp.sdp.sdp_name}"


@description.register
def _mdp2p_description(mdp2p: MultiDomainPoint2PointProvisioning) -> str:
    return f"{mdp2p.product.tag} {mdp2p.vc.circuit_description}"
