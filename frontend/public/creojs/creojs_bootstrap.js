(function () {
    CreoJSBoot.include = function (loads, onCompleteLoad) {
        function onLoad () {
            var next = loads.shift()
            //alert ('Loading ' + JSON.stringify (next))
            if (next) {
                if (next.link) {
                    load (link (next.link, next.type, next.rel), next.link)
                }
                else if (next.script) {
                    load (script (next.script, next.type), next.script)
                }
            }
            else {
                if (onCompleteLoad) onCompleteLoad (CreoJSBoot)
            } 
        }
        function load (elem, src) {
            elem.onload = onLoad
            elem.onerror = function () {
                if (confirm ('Error loading ' + elem.tagName + ': src=' + src + '\nContinue execution?')) onLoad ()
            }
            document.head.appendChild (elem)
        }
        function link (href, type, rel) {
            rel = rel || 'stylesheet'
            type = type || 'text/css'
            var elem = document.createElement ('link')
            elem.rel = rel
            elem.href = href
            return elem
        }
        function script (src, type) {
            type = type || 'text/javascript'
            var elem = document.createElement ('script')
            elem.type = type
            elem.src = src
            return elem
        }
        onLoad ()
    }

    var base = CreoJSBoot.base + '/'
    var loads = []
    function addInclude (include) {
        if (typeof include === 'string') {
            loads.push ({script: base + include})
        }
        else {
            loads.push (include)
        }
    }
    if (typeof CreoJSInclude !== 'undefined' && CreoJSInclude) {
        for (var idx in CreoJSInclude) {
            addInclude (CreoJSInclude [idx])
        }
    }
    if (CreoJSBoot.args.include) {
        for (var idx in CreoJSBoot.args.include) {
            addInclude (CreoJSBoot.args.include [idx])
        }
    }

    CreoJSBoot.include (loads)
}) ()
