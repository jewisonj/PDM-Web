var retries = 15 // can be too fast
function findCompanies () {
    return document.getElementsByTagName ('os-company-details')
}
function findAuthorizations () {
    return Array.from (document.getElementsByTagName ('button')).filter (function (btn) {
        return btn.getAttribute ('ng-disabled') === 'ConfirmAccessController.waitingForAuthorization'
    })
}
function clickFirst (elems) {
    if (elems && elems.length) {
        elems [0].click ()
        return true
    }
    return false
}
function confirmAccess () {
    try {
        if (clickFirst (findCompanies ()) || clickFirst (findAuthorizations ())) return
    }
    catch (ex) {
        console.log (ex)
    }
    if (retries--) {
        console.log ('Retrying to confirm')
        setTimeout (confirmAccess, 1000)
    }
    else {
        console.log ('Failed to confirm')
    }
}
confirmAccess ()