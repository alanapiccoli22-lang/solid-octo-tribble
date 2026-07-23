# -*- coding: utf-8 -*-

def classFactory(iface):
    """Carrega a classe principal do plugin.

    :param iface: A interface do QGIS (QgisInterface)
    """
    from .dem_to_tactile_plugin import DemToTactilePlugin
    return DemToTactilePlugin(iface)
