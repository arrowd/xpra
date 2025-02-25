#!/usr/bin/env python3
# This file is part of Xpra.
# Copyright (C) 2018-2020 Antoine Martin <antoine@xpra.org>
# Xpra is released under the terms of the GNU GPL v2, or, at your option, any
# later version. See the file COPYING for details.

import os
import unittest

from xpra.util.types import typedict, AdHocStruct
from xpra.util.env import OSEnvContext
from unit.test_util import silence_info
from unit.server.mixins.servermixintest_util import ServerMixinTest


class NetworkStateMixinTest(ServerMixinTest):

    def test_networkstate(self):
        with OSEnvContext():
            os.environ["XPRA_PING_TIMEOUT"] = "1"
            from xpra.server.mixins import networkstate
            from xpra.server.source.networkstate import NetworkStateMixin
            assert NetworkStateMixin.is_needed(typedict({"network-state" : True}))
            opts = AdHocStruct()
            opts.pings = 1
            opts.bandwidth_limit = "1Gbps"
            #the limit for all clients:
            capped_at = 1*1000*1000*1000    #=="1Gbps"
            with silence_info(networkstate):
                self._test_mixin_class(networkstate.NetworkStateServer, opts, {}, NetworkStateMixin)
            self.assertEqual(capped_at, self.mixin.get_info().get("bandwidth-limit"))
            self.handle_packet(("ping", 10))
            self.handle_packet(("ping", -1000))
            self.handle_packet(("ping_echo", 10, 500, 500, 600, 10))
            for v in (None, "foo", 1, 2.0, [], (), set()):
                try:
                    self.handle_packet(("connection-data", v))
                except TypeError:
                    pass
                else:
                    raise Exception("should not allow %s (%s) as connection-data" % (v, type(v)))
            self.handle_packet(("connection-data", {}))
            for v in (None, "foo", 2.0, [], (), set()):
                try:
                    self.handle_packet(("bandwidth-limit", v))
                except TypeError:
                    pass
                else:
                    raise Exception("should not allow %s (%s) as connection-data" % (v, type(v)))
            with silence_info(networkstate, "bandwidthlog"):
                self.handle_packet(("bandwidth-limit", 10*1024*1024))
            def get_limit():
                return self.source.get_info().get("bandwidth-limit", {}).get("setting", 0)
            self.assertEqual(10*1024*1024, get_limit())
            with silence_info(networkstate, "bandwidthlog"):
                self.handle_packet(("bandwidth-limit", networkstate.MAX_BANDWIDTH_LIMIT+1))
            self.assertEqual(min(capped_at, networkstate.MAX_BANDWIDTH_LIMIT), get_limit())
            #test source:
            timeouts = []
            def timeout(*args):
                timeouts.append(args)
            self.source.disconnect = timeout
            assert self.source.get_caps()
            self.source.ping()
            self.source.check_ping_echo_timeout(0, 0)
            #give time for the timeout to fire:
            self.glib.timeout_add(2000, self.main_loop.quit)
            self.main_loop.run()


def main():
    unittest.main()


if __name__ == '__main__':
    main()
