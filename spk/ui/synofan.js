Ext.ns("SynoFan");

Ext.define("SynoFan.Application", {
    extend: "SYNO.SDS.AppInstance",
    appWindowName: "SynoFan.AppWindow",
    defaultWinSize: { width: 1180, height: 760 },
    constructor: function () {
        this.callParent(arguments);
    }
});

Ext.define("SynoFan.AppWindow", {
    extend: "SYNO.SDS.AppWindow",
    layout: "fit",
    defaultWinSize: { width: 1180, height: 760 },
    constructor: function (config) {
        var me = this;
        me.callParent([me.fillConfig(config)]);
    },
    fillConfig: function (config) {
        var iframeHtml = '<iframe src="/webman/3rdparty/synofan/index.html" ' +
            'style="width:100%;height:100%;border:none;background:transparent;"></iframe>';
        return Ext.apply({
            title: "SynoFan",
            width: 1180,
            height: 760,
            minWidth: 960,
            minHeight: 640,
            items: [{
                xtype: "panel",
                border: false,
                html: iframeHtml
            }]
        }, config);
    }
});
