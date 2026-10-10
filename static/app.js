// 少量交互：确认删除、筛选自动提交、表单防重复提交。
document.addEventListener('DOMContentLoaded', function () {
  // 危险操作二次确认
  document.querySelectorAll('form[data-confirm]').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // 筛选下拉改变即提交
  document.querySelectorAll('form.auto-submit select, form.auto-submit input[type=date]')
    .forEach(function (el) {
      el.addEventListener('change', function () { el.form.submit(); });
    });

  // 提交后按钮变灰，避免手抖点两次
  document.querySelectorAll('form').forEach(function (form) {
    form.addEventListener('submit', function () {
      const btn = form.querySelector('button[type=submit]:not([data-nolock])');
      if (btn) { setTimeout(function () { btn.disabled = true; }, 0); }
    });
  });
});
