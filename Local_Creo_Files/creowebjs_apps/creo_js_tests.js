function showSource (url) {
    if (confirm ('Integration with W3Schools Tryit Editor is work in progress. Meanwhile, you can navigate to the page and view its source. Do it?')) {
        window.location = url
    }
    return
    var windowFeatures = "location=yes,resizable=yes,scrollbars=yes,status=yes,height=900,width=1100";
    var helpWindow = window.open ("", "Help", windowFeatures);
    $(function(){
        $.ajax({
            url: url,
            async: false,   // asynchronous request? (synchronous requests are discouraged...)
            cache: false,   // with this, you can force the browser to not make cache of the retrieved data
            dataType: "text",  // jQuery will infer this, but you can set explicitly
            success: function( data, textStatus, jqXHR ) {
                var helpHtml = 
                    '<html>' +
                    '<head>' + 
                    ' <META http-equiv="Content-Type" content="text/html; charset=iso-8859-1">' +
                    ' <title>Source Code for "' + url + '"</title>' + 
                    '</head>' +
                    '<body><pre><code id="source">' + data
                    '</code></pre></body>' +
                    '</html>';
                helpWindow.document.open ();
                helpWindow.document.write (helpHtml);
                helpWindow.document.close ();
            }
        });
    });
}

window.addEventListener ('load', function () {
    var sourceButtons = document.getElementsByClassName('sourceimg');
    for (var idx=0; idx<sourceButtons.length; idx++) {
        sourceButtons[idx].title = 'View Source and Play with It'
    }
})
