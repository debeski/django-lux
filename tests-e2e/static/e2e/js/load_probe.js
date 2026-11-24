// Loaded without `defer` from a project page's {% block scripts %}, the way
// consumer scripts are, to record what such a script can use as it loads.
document.documentElement.dataset.e2eLoadProbe = JSON.stringify({
  bootstrap: typeof (window.bootstrap && window.bootstrap.Modal),
  fileFields: typeof window.initFileFieldWidgets,
});
