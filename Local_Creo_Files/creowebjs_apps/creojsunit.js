// Test helpers encapsulating common behavior when testing Creo JS Bridge interface

// Requires inclusion of the following prior to inclusion of this script:
//  <link rel="stylesheet" href="libs/css/qunit-2.9.2.css">
//  <script src="libs/qunit-2.9.2.js"></script>

// To enable QUnit UI include the following:
// <div id="qunit_ui" style="display:none;">
//     <div id="qunit"></div>
//     <div id="qunit-fixture"></div>
// </div>

(function () {
    // Prevent autostart
    // Original QUnit has QUnit.config.autostart === 'true' as a default but we changed it to 'false'
    // always change when updating QUnit version, otherwise QUnit cannot be loaded asynchronously
    // var started = document.readyState === "complete"
    var started = false
        
    /*
        * Checks asynchronous Creo JS Bridge and expects successful return
        * calls checkResult, if provided, to make additional check of the result value
        */
    QUnit.assertCreoJSThen = function (assert, minMaxWaitCleanupAndCount, creoJSCall, checkResult) {
        var done = assertAsync(assert, minMaxWaitCleanupAndCount)
        creoJSCall.then (function (v) {
            assert.ok (true, "Successful completion of Creo call")
            if (checkResult) checkResult (v, assert)
            if (!minMaxWaitCleanupAndCount.wait) done()
        }).catch (function (ex) {
            assert.ok (false, "Unexpected exception in Creo call: " + ex)
            done()
        })
        return done
    }
    /*
        * Checks asynchronous Creo JS Bridge and expects an execution exception
        * calls checkException, if provided, to make additional check of the exception object
        */
    QUnit.assertCreoJSCatch = function (assert, minMaxWaitCleanupAndCount, creoJSCall, checkException) {
        var done = assertAsync(assert, minMaxWaitCleanupAndCount)
        creoJSCall.then (function (v) {
            assert.ok (false, "Unexpected successful completion of Creo call")
            done()
        }).catch (function (ex) {
            assert.ok (true, "Expected exception in Creo call: " + ex)
            if (checkException) checkException (ex, assert)
            if (!minMaxWaitCleanupAndCount.wait) done()
        })
        return done
    }

    // Misc Utils

    function elapsedSince (startDate) {
        return new Date().getTime()-startDate.getTime()
    }

    function assertAsync (assert, minMaxWaitCleanupAndCount) {
        var minDurationMsecs = minMaxWaitCleanupAndCount.min
        var maxDurationMsecs = minMaxWaitCleanupAndCount.max
        var start = new Date()
        var callCount = 0
        var totalCallCount = minMaxWaitCleanupAndCount.count || 1
        var done = assert.async (totalCallCount)
        if (typeof maxDurationMsecs !== 'undefined') assert.timeout (maxDurationMsecs)
        return function () {
            if (++callCount === totalCallCount) {
                if (typeof minDurationMsecs !== 'undefined') {
                    var duration = elapsedSince (start)
                    assert.ok (duration > minDurationMsecs, 'elapsed execution time (' + duration/1000.0 + ' seconds) > ' + minDurationMsecs/1000.0)
                }
                if (typeof minMaxWaitCleanupAndCount.cleanup === 'function')
                    minMaxWaitCleanupAndCount.cleanup()
            }
            done ()
        }
    }

    function getHtmlPageFileName () {
        return window.location.pathname.replace(/^.*[\\\/]/, '')
    }

    var runMode = null

    QUnit.setRunMode  = function (mode) {
        runMode = mode
    }

    QUnit.getRunMode  = function () {
        return runMode || Creo.$PARM ('automation') || 'trail'
    }

    QUnit.autosetup  = function (resultsCB) {
        var runMode = QUnit.getRunMode ()
        if (QUnit.config.autostart) {
            var error = 'QUnit.config.autostart === true; Change default in QUnit to false - requires modification of qunit-#-#-#.js'
            switch (runMode) {
                case 'ui': case 'log': alert (error); break
                default: Creo.regTrail.outOfSequence (error); break
            }
        }
        if (!started) {
            started = true
            QUnit.start()
        }
        switch (runMode) {
            case 'ui': QUnit.showUI (); break
            case 'log': QUnit.setupForLogging (); break
            default: QUnit.setupForCreoRegressionRun (resultsCB); break
        }
    }

    QUnit.testDone (function (details) {
        var result = details.todo ? 'todo' : details.skipped ? 'skipped' : details.failed ? 'failed' : 'passed'
        var summary = {total: details.total, passed: details.passed, failed: details.failed, runtime: details.runtime}
        return Creo.regTrail.setMessage ('QUnit test "' + details.name + '" ' + result + ': summary=' + JSON.stringify (summary))
    })

    QUnit.showUI  = function (show) {
        var uidiv = $('#qunit_ui')
        if (typeof show === 'undefined' || show) {
            uidiv.show()
        } else {
            uidiv.hide()
        }
    }

    QUnit.setupForLogging  = function () {
        QUnit.done(function( details ) {
            CreoJSON.showObject (details)
        })
        QUnit.log(function( details ) {
            CreoJSON.showObject (details)
        })
    }

    QUnit.setupForCreoRegressionRun  = function (resultsCB) { // function resultsCB (id, log) -> bool (proceed)
        function somethingWentWrongWith (eventMessage) {
            return function (ok) {if (!ok) alert ('Something went wrong with ' + eventMessage)}
        }
        var trailTag = 'CreoJSBridgeRegRun'
        var id = getHtmlPageFileName ()
        Creo.regTrail.setMessage ('Starting QUnit run "' + id + '"')
        function synchronizeTrail () {
            Creo.regTrail.syncTag (trailTag, true).then (somethingWentWrongWith ('syncing tag ' + trailTag))
        }
        var log = {asserts: []}
        QUnit.done(function (details) {
            log.summary = details
            if (resultsCB) if (!resultsCB (id, log)) return
            if (details.failed) {
                Creo.regTrail.outOfSequence ('QUnit run "' + id + '" failed: summary=' + JSON.stringify (details))
                    .then (function (ok) {if (!ok) alert ('Something went wrong with forcing OOS')})
                    .finally (synchronizeTrail)
            }
            else {
                Creo.regTrail.setMessage ('QUnit run "' + id + '" succeeded: summary=' + JSON.stringify (details))
                    .finally (synchronizeTrail)
            }
        })
        QUnit.log(function (details) {
            log.asserts.push (details)
        })
    }

}) ()
