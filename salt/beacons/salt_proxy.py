"""
    Beacon to manage and report the status of
    one or more salt proxy processes

    .. versionadded:: 2015.8.3
"""

import logging

import salt.utils.beacons

log = logging.getLogger(__name__)


def _run_proxy_processes(proxies):
    """
    Iterate over a list of proxy
    names and restart any that
    aren't running
    """
    ret = []
    for proxy in proxies:
        result = {}
        if not __salt__["salt_proxy.is_running"](proxy)["result"]:
            __salt__["salt_proxy.configure_proxy"](proxy, start=True)
            result[proxy] = f"Proxy {proxy} was started"
        else:
            msg = f"Proxy {proxy} is already running"
            result[proxy] = msg
            log.debug(msg)
        ret.append(result)
    return ret


def validate(config):
    """
    Validate the beacon configuration
    """
    # Configuration for adb beacon should be a dictionary with states array
    if not isinstance(config, list):
        log.info("Configuration for salt_proxy beacon must be a list.")
        return False, "Configuration for salt_proxy beacon must be a list."

    else:
        config = salt.utils.beacons.list_to_dict(config)

        if "proxies" not in config:
            return False, "Configuration for salt_proxy beacon requires proxies."
        else:
            if not isinstance(config["proxies"], dict):
                return False, "Proxies for salt_proxy beacon must be a dictionary."
    return True, "Valid beacon configuration"


def beacon(config):
    """
    Handle configured proxies

    .. code-block:: yaml

        beacons:
          salt_proxy:
            - proxies:
                p8000: {}
                p8001: {}
    """
    log.trace("salt proxy beacon called")

    config = salt.utils.beacons.list_to_dict(config)

    return _run_proxy_processes(config["proxies"])
