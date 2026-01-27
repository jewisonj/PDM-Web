
// JSON visualization helpers

// Requires inclusion of the following prior to inclusion of this script:
// <head> ...
// <link rel="stylesheet" type="text/css" href="libs/css/pretty-json.css" />
// <script type="text/javascript" src="libs/underscore-min.js"></script>
// <script type="text/javascript" src="libs/backbone-min.js"></script>
// <script type="text/javascript" src="libs/pretty-json-min.js"></script>

// To enable JSON vizualization UI include the following:
// <div id="json_output"></div>

var CreoJSON = (function () {
    function buildViewer (obj) {
        var too = typeof obj
        if (too !== 'object') {
            var value = obj
            obj = {}
            obj [too] = value
        }
        var span = document.createElement('span')
        return {
            element: span,
            view: new PrettyJSON.view.Node({
                el: span,
                data: obj
            })
        }
    }
    function insertJson (div, obj, first, title, closebtn, footer) {
        var frame = document.createElement('span')
        if (title) {
            if (closebtn) {
                var close;
                if (typeof closebtn === 'string') {
                    close = document.createElement ('img')
                    close.src = closebtn
                    close.style = 'vertical-align:middle'
                    close.onclick = function () {
                        div.removeChild (frame)
                    }
                }
                else {
                    close = document.createElement ('input')
                    close.type = "checkbox"
                    close.checked = true
                    close.onchange = function () {
                        if (!close.checked) div.removeChild (frame)
                    }
                }
                frame.appendChild (close)
            }
            if (title instanceof HTMLElement) {
                frame.appendChild (title)
            }
            else {
                frame.appendChild (document.createTextNode(title + ': '))
            }
        }
        var viewer = buildViewer (obj)
        frame.appendChild (viewer.element)
        if (footer) {
            if (footer instanceof HTMLElement) {
                frame.appendChild (footer)
            }
            else {
                frame.appendChild (document.createTextNode(' ' + footer))
            }
        }
        frame.appendChild (document.createElement('br'))
        div.insertBefore (frame, first ? div.firstChild : null)
        return viewer.view
    }
    function showJson (obj, divid, title, closebtn, footer) {
        return insertJson (document.getElementById(divid || 'json_output'), obj, false, title, closebtn, footer)
    }
    function pushJson (obj, divid, title, closebtn, footer) {
        return insertJson (document.getElementById(divid || 'json_output'), obj, true, title, closebtn, footer)
    }
    function clearJson (divid) {
        var div = document.getElementById(divid || 'json_output')
        if (div) div.innerHTML = ""
    }
    function showFailure (value)
    {
        showObject ({
            exception: value
        })
        //alert ("Failure: " + JSON.stringify (value))
    }
    function showDebugCall (name, args)
    {
        showObject ({
            calling: name,
            args: Array.prototype.slice.call (args, 0)
        })
    }
    function showObject (obj)
    {
        showJson (obj).expandAll ()
    }
    function showResult (promise)
    {
        if ('then' in promise) {
            promise.then (showObject).catch (showFailure)
        }
        else {
            showObject (promise)
        }
    }
    return {
        makeJsonViewer: buildViewer,
        showJson: showJson,
        pushJson: pushJson,
        showObject: showObject,
        clearJson: clearJson,
        showFailure: showFailure,
        showDebugCall: showDebugCall,
        showResult: showResult
    }
}) ()
