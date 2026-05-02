def classFactory(iface):
    from .qgis_standard_mcp_plugin import QGISStandardMCPPlugin
    return QGISStandardMCPPlugin(iface)
