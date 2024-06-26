"""
Cobbler Tops
============

Cobbler Tops is a master tops subsystem used to look up mapping information
from Cobbler via its API. The same cobbler.* parameters are used for both
the Cobbler tops and Cobbler pillar modules.

.. code-block:: yaml

  master_tops:
    cobbler: {}
  cobbler.url: https://example.com/cobbler_api #default is http://localhost/cobbler_api
  cobbler.user: username # default is no username
  cobbler.password: password # default is no password


Module Documentation
====================
"""

import logging
import xmlrpc.client  # nosec

log = logging.getLogger(__name__)


__opts__ = {
    "cobbler.url": "http://localhost/cobbler_api",
    "cobbler.user": None,
    "cobbler.password": None,
}


def top(**kwargs):
    """
    Look up top data in Cobbler for a minion.
    """
    url = __opts__["cobbler.url"]
    user = __opts__["cobbler.user"]
    password = __opts__["cobbler.password"]

    minion_id = kwargs["opts"]["id"]

    log.info("Querying cobbler for information for %r", minion_id)
    try:
        server = xmlrpc.client.Server(url, allow_none=True)
        if user:
            server.login(user, password)
        data = server.get_blended_data(None, minion_id)
    except Exception:  # pylint: disable=broad-except
        log.exception("Could not connect to cobbler.")
        return {}

    return {data["status"]: data["mgmt_classes"]}
