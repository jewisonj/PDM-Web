var Creo  = (function () {
    var JSBridgeCaller = function (name) {
        if (typeof Promise === 'undefined') {
            Promise$JS = (function () {
                function NOOP() {}
        
                // States:
                var PENDING = 0;
                var FULFILLED = 1;
                var REJECTED = 2;
                var ADOPTED = 3;
        
                // to avoid using try/catch inside critical functions, we
                // extract them to here.
                var LAST_ERROR = null;
                var IS_ERROR = {};
        
                function getThen(obj) {
                    try {
                        return obj.then;
                    } catch (ex) {
                        LAST_ERROR = ex;
                        return IS_ERROR;
                    }
                }
        
                function tryCallOne(fn, a) {
                    try {
                        return fn(a);
                    } catch (ex) {
                        LAST_ERROR = ex;
                        return IS_ERROR;
                    }
                }
        
                function tryCallTwo(fn, a, b) {
                    try {
                        fn(a, b);
                    } catch (ex) {
                        LAST_ERROR = ex;
                        return IS_ERROR;
                    }
                }
        
                function Promise(fn) {
                    if (typeof this !== 'object') {
                        throw new TypeError('Promises must be constructed via new');
                    }
                    if (typeof fn !== 'function') {
                        throw new TypeError('Promise constructor\'s argument is not a function');
                    }
                    this._deferredState = PENDING;
                    this._state = PENDING;
                    this._value = null;
                    this._deferreds = null;
                    if (fn === NOOP) return;
                    doResolve(fn, this);
                }
        
                Promise._onHandle = null;
                Promise._onReject = null;
                Promise._noop = NOOP;
        
                Promise.prototype.then = function(onFulfilled, onRejected) {
                    if (this.constructor !== Promise) {
                        return safeThen(this, onFulfilled, onRejected);
                    }
                    var res = new Promise(NOOP);
                    handle(this, new Handler(onFulfilled, onRejected, res));
                    return res;
                };
        
                Promise.prototype.catch = function(onRejected) {
                    return this.then (undefined, onRejected);
                };
        
                Promise.prototype.finally = function(handler) {
                    return this.then (handler, handler);
                };
        
                function safeThen(self, onFulfilled, onRejected) {
                    return new self.constructor(function (resolve, reject) {
                        var res = new Promise(NOOP);
                        res.then(resolve, reject);
                        handle(self, new Handler(onFulfilled, onRejected, res));
                    });
                }
        
                function handle(self, deferred) {
                    while (self._state === ADOPTED) {
                        self = self._value;
                    }
                    if (Promise._onHandle) {
                        Promise._onHandle(self);
                    }
                    if (self._state === PENDING) {
                        if (self._deferredState === PENDING) {
                            self._deferredState = FULFILLED;
                            self._deferreds = deferred;
                            return;
                        }
                        if (self._deferredState === FULFILLED) {
                            self._deferredState = REJECTED;
                            self._deferreds = [self._deferreds, deferred];
                            return;
                        }
                        self._deferreds.push(deferred);
                        return;
                    }
                    handleResolved(self, deferred);
                }
        
                function handleResolved(self, deferred) {
                    setTimeout(function() {
                        var cb = self._state === FULFILLED ? deferred.onFulfilled : deferred.onRejected;
                        if (cb === null) {
                        if (self._state === FULFILLED) {
                            resolve(deferred.promise, self._value);
                        } else {
                            reject(deferred.promise, self._value);
                        }
                        return;
                        }
                        var ret = tryCallOne(cb, self._value);
                        if (ret === IS_ERROR) {
                            reject(deferred.promise, LAST_ERROR);
                        } else {
                            resolve(deferred.promise, ret);
                        }
                    }, 0);
                }
        
                function resolve(self, newValue) {
                    // Promise Resolution Procedure: https://github.com/promises-aplus/promises-spec#the-promise-resolution-procedure
                    if (newValue === self) {
                        return reject(
                            self,
                            new TypeError('A promise cannot be resolved with itself.')
                        );
                    }
                    if (newValue && (typeof newValue === 'object' || typeof newValue === 'function')) {
                        var then = getThen(newValue);
                        if (then === IS_ERROR) {
                            return reject(self, LAST_ERROR);
                        }
                        if (then === self.then && newValue instanceof Promise) {
                            self._state = ADOPTED;
                            self._value = newValue;
                            finale(self);
                            return;
                        } else if (typeof then === 'function') {
                            doResolve(then.bind(newValue), self);
                            return;
                        }
                    }
                    self._state = FULFILLED;
                    self._value = newValue;
                    finale(self);
                }
        
                function reject(self, newValue) {
                    self._state = REJECTED;
                    self._value = newValue;
                    if (Promise._onReject) {
                        Promise._onReject(self, newValue);
                    }
                    finale(self);
                }
        
                function finale(self) {
                    if (self._deferredState === FULFILLED) {
                        handle(self, self._deferreds);
                        self._deferreds = null;
                    }
                    if (self._deferredState === REJECTED) {
                        for (var i = 0; i < self._deferreds.length; i++) {
                            handle(self, self._deferreds[i]);
                        }
                        self._deferreds = null;
                    }
                }
        
                function Handler(onFulfilled, onRejected, promise){
                    this.onFulfilled = typeof onFulfilled === 'function' ? onFulfilled : null;
                    this.onRejected = typeof onRejected === 'function' ? onRejected : null;
                    this.promise = promise;
                }
        
                /**
                 * Take a potentially misbehaving resolver function and make sure
                 * onFulfilled and onRejected are only called once.
                 *
                 * Makes no guarantees about asynchrony.
                 */
                function doResolve(fn, promise) {
                    var done = false;
                    var res = tryCallTwo(fn, function (value) {
                        if (done) return;
                        done = true;
                        resolve(promise, value);
                    }, function (reason) {
                        if (done) return;
                        done = true;
                        reject(promise, reason);
                    });
                    if (!done && res === IS_ERROR) {
                        done = true;
                        reject(promise, LAST_ERROR);
                    }
                }
        
                return Promise
            }) ()
        }
        else {
            Promise$JS = Promise
        }

        this.$PROMISE = Promise$JS

        function isPromise (obj) {
            return obj && (typeof obj === 'object') &&
                (typeof obj ['then'] === 'function') &&
                (typeof obj ['catch'] === 'function') &&
                (typeof obj ['finally'] === 'function')
        }

        var GUID = GUID || (function() {
            var crypto = window.crypto || window.msCrypto || null; // IE11 fix
    
            var EMPTY = '00000000-0000-0000-0000-000000000000';
    
            var _padLeft = function(paddingString, width, replacementChar) {
                return paddingString.length >= width ? paddingString : _padLeft(replacementChar + paddingString, width, replacementChar || ' ');
            };
    
            var _s4 = function(number) {
                var hexadecimalResult = number.toString(16);
                return _padLeft(hexadecimalResult, 4, '0');
            };
    
            var _cryptoGuid = function() {
                var buffer = new window.Uint16Array(8);
                crypto.getRandomValues(buffer);
                return [_s4(buffer[0]) + _s4(buffer[1]), _s4(buffer[2]), _s4(buffer[3]), _s4(buffer[4]), _s4(buffer[5]) + _s4(buffer[6]) + _s4(buffer[7])].join('-');
            };
    
            var _guid = function() {
                var currentDateMilliseconds = new Date().getTime();
                return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(currentChar) {
                    var randomChar = (currentDateMilliseconds + Math.random() * 16) % 16 | 0;
                    currentDateMilliseconds = Math.floor(currentDateMilliseconds / 16);
                    return (currentChar === 'x' ? randomChar : (randomChar & 0x7 | 0x8)).toString(16);
                });
            };
    
            var create = function() {
                var hasCrypto = crypto != 'undefined' && crypto !== null,
                hasRandomValues = typeof(crypto.getRandomValues) != 'undefined';
                return (hasCrypto && hasRandomValues) ? _cryptoGuid() : _guid();
            };
    
            return {
                newGuid: create,
                empty: EMPTY
                };
        })();
        var prefix = name + '?'
        var client = GUID.newGuid();
        var callCount = 0;
        var calls = {}
        var functions = {}
        var frameLocator = null
        var frameId = '_top'
        function makeCallData (command, id, more) {
            var metadata = {}
            metadata.client = client
            metadata.id = String (id)
            metadata.resource = 'page'
            metadata.command = command
            metadata.frameId = frameId
            if (frameLocator) {
                metadata.frameLocator = frameLocator
                frameLocator = null
            }
            if (more) for (var name in more) metadata [name] = more [name]
            return metadata;
        }
        function makeFunctionData (func) {
            if ('&' in func) {
                return func ['&']
            }
            var id = callCount++
            functions [id] = func
            var funcdata = {id: id, context: client};
            funcdata ['$$type'] = 'function'
            return funcdata
        }
        function adoptRemoteValue (value) {
            if (value && (typeof value === 'object') && (value ['$$type'] === 'function'))
            {
                // alert (JSON.stringify ({where: "adoptRemoteValue", value: value}))
                var cb = makeCallable ('lambda', value).$ (value.id)
                cb ['&'] = value
                cb.destroy = function () {
                    makeCall (makeCallData ('destroy', 'lambda', {lambda: value}))
                }
                return cb
            }
            return value
        }
        function prepareRemoteValue (value) {
            if (typeof value === 'function') {
                return makeFunctionData (value)
            }
            return value
        }

        var isCreoAvailable = window.external && window.external.ptc && (typeof window.external.ptc !== 'undefined');
        
        var checkedAvailability = false
        function makeCall (metadata) {
            if (!checkedAvailability) {
                checkedAvailability = true
                if (!isCreoAvailable) {
                    alert ('The page attempts to access Creo environment which is not supported by your browser. Some functionalty may not be available')
                }
            }
            if (isCreoAvailable) {
                // alert ('makeCall: ' + JSON.stringify (metadata))
                window.external.ptc (prefix + JSON.stringify (metadata));
                return true
            }
            return false
        }
        function makeCallable (type, name)
        {
            var callableName = name;
            return {
                call: function (name) {
                    var args = Array.prototype.slice.call (arguments)
                    args.shift()
                    return this.$ (name).apply (null, args)
                },
                $: function (name) {
                    var method = this [name]
                    if (!method) this [name] = method = function () {
                        var args = Array.prototype.slice.call (arguments).map (prepareRemoteValue)
                        var metadata = makeCallData ('call', callCount++, {
                            funcName: name,
                            args: args
                        })
                        metadata[type] = callableName
                        var callId = metadata.id
                        var call = {id: callId}
                        calls [callId] = call
                        // alert ('making call ' + JSON.stringify (metadata))
                        if (makeCall (metadata)) {
                            return new Promise$JS (function (resolve, reject) {
                                call.resolve = resolve
                                call.reject = reject
                            })
                        }
                        else {
                            return new Promise$JS (function (resolve, reject) {
                                reject ("Not connected to Creo")
                            })
                        }
                    }
                    return method
                }
            }
        }
        this.isAvailable = function () {return isCreoAvailable}
        this.import = function (module, calls) {
            var m = this.module (module)
            for (var idx = 1; idx < arguments.length; idx++) m.$ (arguments [idx])
        }
        this.module = function (name) {
            var module = this [name]
            if (!module) module = this [name] = makeCallable ('moduleName', name)
            return module
        }
        this.object = function (name) {
            var object = this [name]
            if (!object) object = this [name] = makeCallable ('objName', name)
            return object
        }
        this.require = function () {
            return this.module ("CreoJsBridgeInterface")
                .call ("require", Array.prototype.slice.call (arguments))
                //.catch (function (exc) {alert (JSON.stringify (exc))})
        }
        var creojs_id = null
        this.$INITIALIZE = function (connectionId) {
            creojs_id = connectionId
            completeInitialization ()
        }
        this.$ONADD = function (features) {
            //alert ('Adding features: ' + JSON.stringify (features))
            //alert ("before: " + JSON.stringify (Object.keys(this)))
            for (var i = 0; i < features.length; i++) {
                var item = features [i]
                var feature = makeCallable (item.type, item.name)
                var methods = item.methods
                for (var j = 0; j < methods.length; j++) {
                    feature.$ (methods [j])
                }
                //alert ('Adding [' + item.name + ']:' + JSON.stringify (item))
                this [item.name] = feature
            }
            //alert ("after: " + JSON.stringify (Object.keys(this)))
        }
        this.$ONDELETE = function (features) {
            for (var i = 0; i < features.length; i++) {
                delete this [features [i]]
            }
        }
        this.$ONRESPONSE = function (response) {
            // alert ('ONRESPONSE: ' + JSON.stringify (response))
            if (response && response.result && response.result.client == client)
            {
                var result = response.result
                var call = calls [result.id]
                if (call) {
                    var value = result.value
                    if (value.success) {
                        if (call.resolve) call.resolve (adoptRemoteValue (value.result))
                    }
                    else {
                        if (call.reject) call.reject (value.message)
                    }
                    delete calls [response.id]
                }
            }
        }
        this.$ONERROR = function (message) {
            alert ("JavaScript Brigde Failure: " + message)
        }
        this.$ONRELEASE = function (message) {
            // alert ('ONRELEASE: ' + JSON.stringify (message))
            if (message && message.release && message.release.client == client) {
                delete functions [message.release.id]
            }
        }
        // options: {frameId: fid, frameLocator: locator, origin: url}
        this.$SET_IFRAME_SERVER = function (options) {
            if (options) {
                var fid = options.frameId
                var locator = options.frameLocator
                if (fid || locator) {
                    var origin = options.origin || location.origin
                    var THIS = this
                    frameId = fid || locator
                    frameLocator = locator || 'document.getElementById ("' + fid + '")'
                    // alert ('SET_IFRAME_SERVER: frameLocator: ' + JSON.stringify (frameLocator) + ' frameId: ' + JSON.stringify (frameId))
                    window.addEventListener('message', function (e) {
                        // alert ('iframe message: ' + JSON.stringify (e.data))
                        var eventOrigin = e.origin;
                        if (eventOrigin == "file:") {
                            /*
                            * IE sends "file:" while Chrome send "file://"
                            * In location.origin both browosers have "file://"
                            */
                            eventOrigin += "//";
                        }
                        if (origin === eventOrigin) {
                            var data = e.data
                            if (data && data.CreoJS) {
                                THIS [data.CreoJS] (data.args)
                            }
                        }
                    }, false)
                }
            }
        }

        var callParser = /((.*)\.)*(.+)/
        this.$ONCALL = function (message) {
            // alert ("oncall " + JSON.stringify(message))
            if (message && message.call && message.call.client == client) {
                var call = message.call;
                var id = call.id;
                var metadata = makeCallData ("result", id);
                var funcdata = call.name.match (callParser)
                if (funcdata) {
                    var targetObj = funcdata [2]
                    var funcname = funcdata [3]
                    try {
                        var obj = null
                        var func = null
                        if (targetObj) {
                            obj = eval (targetObj)
                            if (!obj) throw '"' + targetObj + '" not found'
                            func = obj [funcname]
                        }
                        else {
                            if (funcname.lastIndexOf ('&', 0) === 0) {
                                func = functions [funcname.substr(1)]
                            }
                            else {
                                func = eval (funcname)
                            }
                        }
                        if (typeof func === 'function') {
                            var res = func.apply (obj, call.args.map (adoptRemoteValue)) || null
                            if (isPromise (res)) {
                                res.then (function (res) {
                                    metadata.value = prepareRemoteValue (res)
                                    metadata.success = true;
                                }).catch (function (exc) {
                                    metadata.success = false;
                                    metadata.exception = String (exc);
                                }).finally (function () {
                                    makeCall (metadata);
                                })
                                return
                            }
                            metadata.value = prepareRemoteValue (res)
                            metadata.success = true;
                        }
                        else {
                            metadata.success = false;
                            metadata.exception = '"' + call.name + '" not a function'
                        }
                    }
                    catch (ex) {
                        // alert (JSON.stringify({exc:ex}))
                        metadata.success = false;
                        metadata.exception = ex.toString();
                    }
                }
                else {
                    metadata.success = false;
                    metadata.exception = 'wrong call format "' + call.name + '"'
                }
                makeCall (metadata);
            }
        }
        this.$PARM = function (name) {
            var url = window.location.href;
            name = name.replace(/[\[\]]/g, '\\$&');
            var regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)'),
                results = regex.exec(url);
            if (!results) return undefined;
            if (!results[2]) return '';
            return decodeURIComponent(results[2].replace(/\+/g, ' '));
        }
        creojs_id = this.$PARM ("creojs_id")
        function completeInitialization () {
            if ((window !== window.top) && !frameLocator) {
                alert ("ERROR: Initializing Creo JS Bridge in non-top frame without defining frame locator")
            }
            else if (!creojs_id) {
                alert ("ERROR: Connection id is not specified for Creo JS Bridge initialization")
            }
            else {
                makeCall (makeCallData ("register", creojs_id))
                executeLoadListeners ()
            }
        }

        window.addEventListener ('load', function () {
            if (creojs_id)
            {
                if (typeof $completeCreoJSInitialization === 'function') {
                    $completeCreoJSInitialization (completeInitialization)
                }
                else {
                    completeInitialization ()
                }
            }
            else {
                executeLoadListeners ()
            }
        })

        window.addEventListener ('unload', function () {
            makeCall (makeCallData ('release', frameId))
            isCreoAvailable = false
            executeUnloadListeners ()
        })

        var onLoadListeners = []
        var onUnloadListeners = []
        function executeLoadListeners () {
            onLoadListeners.forEach (function (cb) { cb () })
        }
        function executeUnloadListeners () {
            onUnloadListeners.forEach (function (cb) { cb () })
        }
        this.$ONLOAD = function (cb) {
            onLoadListeners.push (cb)
        }
        this.$ONUNLOAD = function (cb) {
            onUnloadListeners.push (cb)
        }
    }

    return new JSBridgeCaller ('CallCreoModule')
}) ()

function $addToCreoJSContext (features) {Creo.$ONADD (features)}
function $deleteFromCreoJSContext (features) {Creo.$ONDELETE (features)}

if (typeof CreoJS === 'undefined') CreoJS = Creo
