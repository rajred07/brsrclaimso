'use strict';

B.on(document, 'allGood', function () {
    console.log('bussiness-sustainabilitiy-reports-csp file loaded');

    // Refresh button
    var refreshButton = document.getElementById('refresh_CFBussinessSustainabilitiy');
    if (refreshButton) {
        refreshButton.addEventListener('click', function (e) {
            e.preventDefault();
            CFRefreshBusiness('CFBussinessSustainabilitiy');
        });
    }

    // Download CSV button
    var downloadButton = document.getElementById('CFBussinessSustainabilitiy-download');
    if (downloadButton) {
        downloadButton.addEventListener('click', function (e) {
            e.preventDefault();
            downloadCSV('CFBussinessSustainabilitiy-download');
        });
    }

    // Pagination buttons for Equity tab (top)
    var equityPaginationButtons = [{ id: 'first1', handler: function handler(e) {
            e.preventDefault();
            onFirstClickCFBussinessSustainabilitiy();
        } }, { id: 'prev1', handler: function handler(e) {
            e.preventDefault();
            onPrevClickCFBussinessSustainabilitiy();
        } }, { id: 'next1', handler: function handler(e) {
            e.preventDefault();
            onNextClickCFBussinessSustainabilitiy();
        } }, { id: 'last1', handler: function handler(e) {
            e.preventDefault();
            onLastClickCFBussinessSustainabilitiy();
        } }];

    equityPaginationButtons.forEach(function (btn) {
        var element = document.getElementById(btn.id);
        if (element) {
            element.addEventListener('click', btn.handler);
        }
    });

    // Pagination buttons for Equity tab (bottom)
    var equityPaginationButtonsBottom = [{ id: 'first', handler: function handler(e) {
            e.preventDefault();
            onFirstClickCFBussinessSustainabilitiy();
        } }, { id: 'prev', handler: function handler(e) {
            e.preventDefault();
            onPrevClickCFBussinessSustainabilitiy();
        } }, { id: 'next', handler: function handler(e) {
            e.preventDefault();
            onNextClickCFBussinessSustainabilitiy();
        } }, { id: 'last', handler: function handler(e) {
            e.preventDefault();
            onLastClickCFBussinessSustainabilitiy();
        } }];

    equityPaginationButtonsBottom.forEach(function (btn) {
        var element = document.getElementById(btn.id);
        if (element) {
            element.addEventListener('click', btn.handler);
        }
    });

    // Pagination input handlers for Equity tab (top)
    var equityPageInput = document.getElementById('goToPageNum1CFBussinessSustainabilitiy');
    if (equityPageInput) {
        equityPageInput.addEventListener('blur', function () {
            goToPageNumCFBussinessSustainabilitiy('top');
        });
        equityPageInput.addEventListener('keyup', function (e) {
            goToPage(e, 'top');
        });
    }

    // Pagination input handlers for Equity tab (bottom)
    var equityPageInputBottom = document.getElementById('goToPageNumCFBussinessSustainabilitiy');
    if (equityPageInputBottom) {
        equityPageInputBottom.addEventListener('blur', function () {
            goToPageNumCFBussinessSustainabilitiy('bottom');
        });
        equityPageInputBottom.addEventListener('keyup', function (e) {
            goToPage(e, 'bottom');
        });
    }
});