(function () {
    var base = CreoJSBoot.base + '/'
    CreoJSBoot.include ([
        // jQuery is a foundation for Pretty JSON and QUnit
        {script: base + 'libs/jquery-3.3.1.min.js'},
        // QUnit related includes
        {link: base + 'libs/css/qunit-2.9.2.css'},
        {script: base + 'libs/qunit-2.9.2.js'},
        // Pretty JSON related includes
        {link: base + 'libs/css/pretty-json.css'},
        {script: base + 'libs/underscore-min.js'},
        {script: base + 'libs/backbone-min.js'},
        {script: base + 'libs/pretty-json-min.js'},
        // CreoJS Bridge and testing frameworks (Pretty JSON and QUnit extensions)
        {script: base + 'creojsbridge.js'},
        {script: base + 'creojsunit.js'},
        {script: base + 'creojson.js'}
    ], function (args) {
        Creo.require ('regTrail').then (function () {
            unitTest (args)
        })
    })
}) ()
