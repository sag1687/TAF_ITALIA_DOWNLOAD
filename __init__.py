# -*- coding: utf-8 -*-
def classFactory(iface):
    from .agenzia_taf_plugin import AgenziaTafPlugin

    return AgenziaTafPlugin(iface)
