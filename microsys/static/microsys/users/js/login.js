
// Hide the login button in the title bar if present.
document.addEventListener("DOMContentLoaded", function() {
    var loginTitleButton = document.querySelector(".login-title-btn");
    if (loginTitleButton) {
        loginTitleButton.style.display = "none";
    }

    // Autofocus on username field
    var usernameField = document.getElementById("username");
    if (usernameField) {
        usernameField.focus();
    }

});
