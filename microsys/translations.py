# microsys/translations.py
# ========================
# Lightweight translation string table for the microsys framework.
# Developers can override any key via System Settings in the UI,
# or add new language dicts entirely. This dict is unlimited — add as many keys as needed.
#
# Usage in templates:  {{ MS_TRANS.key_name }}
# Usage in Python:     from microsys.translations import get_strings
#                      strings = get_strings('en')

MICROSYS_STRINGS = {
    # ───────────────────────────── Arabic (default) ─────────────────────────────
    'ar': {
        # Titlebar
        'help': 'مساعدة',
        'tour_title': 'جولة تعريفية',
        'profile': 'الملف الشخصي',
        'logout': 'تسجيل الخروج',
        'login': 'تسجيل الدخول',

        # Login page
        'username': 'اسم المستخدم',
        'password': 'كلمة المرور',
        'login_submit': 'دخول',
        'login_logo_alt': 'شعار تسجيل الدخول',

        # Dashboard
        'dashboard_welcome': 'مرحباً بك في النظام المتكامل لإدارة الموارد العامة.',
        'greeting_morning': 'صباح الخير',
        'greeting_afternoon': 'مساء الخير',
        'greeting_evening': 'طابت ليلتك',
        'app_core': 'الرئيسية',
        'app_storage': 'إدارة المخازن',
        'app_storage_desc': 'إدارة الأصول، المخازن، وحركة الأصناف.',
        'app_finance': 'إدارة المالية',
        'app_finance_desc': 'إدارة الميزانية، الأبواب، والمناقلات المالية.',
        'app_treasury': 'الخزينة',
        'app_treasury_desc': 'إدارة الإيرادات، المصروفات، والعهد المالية.',
        'app_hr_payroll': 'الموارد البشرية والمرتبات',
        'app_salary': 'المرتبات',
        'app_salary_desc': 'إدارة بطاقات المرتبات، الإستقطاعات، وكشوف المرتبات.',
        'sidebar_system_desc': 'إدارة المستخدمين، الصلاحيات، وإعدادات المنظومة.',
        'contact_admin': 'الرجاء التواصل مع مدير النظام للحصول على صلاحيات الوصول.',
        'work_scope': 'نطاق العمل',
        'manage_users': 'إدارة المستخدمين',
        'manage_users_desc': 'إدارة حسابات المستخدمين والصلاحيات.',
        'manage_sections': 'إدارة الأقسام',
        'manage_sections_desc': 'هيكلة الأقسام والجهات والوحدات الإدارية.',
        'activity_log': 'سجل النشاط',
        'activity_log_desc': 'متابعة نشاطات المستخدمين والتغييرات.',
        'settings': 'الإعدادات',
        'settings_desc': 'خيارات النظام ومعلومات النسخة.',
        'profile_desc': 'عرض وتعديل بيانات ملفك الشخصي.',
        'go': 'الذهاب',
        'activity_24h': 'النشاط (آخر 24 ساعة)',
        'system_settings_title': 'إعدادات النظام العامة',
        'system_settings_label': 'إعدادات النظام',
        'system_settings_btn': 'إدارة إعدادات النظام',
        'system_settings_desc': 'تهيئة إعدادات المنظومة العامة والافتراضيات.',
        'system_settings_export': 'تصدير ملف التهيئة',
        'system_settings_modal_desc': 'حدّث الهوية واللغات والشريط الجانبي ومظهر الواجهة من نافذة الإعدادات.',
        'system_settings_branding': 'الهوية',
        'system_settings_languages': 'اللغات',
        'system_settings_security': 'الوصول والأمان',
        'system_settings_sidebar': 'الشريط الجانبي',
        'system_settings_ui_layout': 'شريط العنوان',
        'system_settings_appearance': 'المظهر والخط',
        'system_setup_title': 'التهيئة الأولى للبرنامج',
        'system_setup_heading': 'ابدأ تهيئة Microsys',
        'system_setup_desc': 'أكمل إعدادات الهوية واللغات والشريط الجانبي والمظهر قبل البدء.',
        'system_setup_page_desc': 'اضبط هوية النظام ولغاته وسلوك الشريط الجانبي ومظهر الواجهة من مكان واحد.',
        'system_setup_step1': 'الخطوة 1: الهوية',
        'system_setup_step2': 'الخطوة 2: اللغات والترجمات',
        'system_setup_step3': 'الخطوة 3: الوصول والأمان',
        'system_setup_step4': 'الخطوة 4: الشريط الجانبي والتنقل',
        'system_setup_step5': 'الخطوة 5: شريط العنوان',
        'system_setup_step6': 'الخطوة 6: المظهر والخط',
        'apply_language': 'تطبيق اللغة',

        # System Settings Form
        'form_sys_system_names': 'أسماء النظام حسب اللغة',
        'form_sys_system_name_placeholder': 'اسم النظام',
        'form_sys_home_url': 'الرابط الرئيسي العام',
        'help_sys_home_url': 'اختر رابط الصفحة الرئيسية الأساسي. يبقى هو وجهة المستخدمين المسجّلين وتوجيه ما بعد تسجيل الدخول حتى لو فُصلت وجهة الجذر العام للمستخدمين غير المسجّلين.',
        'form_sys_home_url_discovered': 'اختر من الصفحات المكتشفة',
        'help_sys_home_url_discovered': 'اختياري: اختر صفحة مكتشفة لتعبئة رابط الصفحة الرئيسية تلقائياً، أو اتركه فارغاً واكتب رابطاً مخصصاً.',
        'form_sys_public_root_url': 'رابط الجذر العام للمستخدم غير المسجّل',
        'help_sys_public_root_url': 'اختياري: عند تفعيل فصل الجذر العام، يُعاد توجيه المستخدمين غير المسجّلين الذين يصلون إلى `/` إلى هذا الرابط بدلاً من رابط الصفحة الرئيسية الأساسي.',
        'form_sys_public_root_url_discovered': 'اختر وجهة الجذر العام من الصفحات المكتشفة',
        'help_sys_public_root_url_discovered': 'اختياري: اختر صفحة مكتشفة لتعبئة وجهة الجذر العام للمستخدم غير المسجّل، أو اتركه فارغاً واكتب رابطاً مخصصاً.',
        'form_sys_home_url_custom': 'استخدم رابطاً مخصصاً أو اترك القيمة الحالية',
        'home_url_custom_desc': 'أبقِ زر الرئيسية موجهاً إلى رابط مخصص بدلاً من صفحة مكتشفة.',
        'selector_search_pages': 'ابحث في الصفحات المكتشفة',
        'form_sys_default_lang': 'اللغة الافتراضية',
        'form_sys_default_theme': 'المظهر الافتراضي',
        'form_sys_allowed_themes': 'المظاهر المسموح بها',
        'help_sys_allowed_themes': 'اختر المظاهر التي تريد السماح بها داخل هذا المشروع. يجب أن يبقى المظهر الافتراضي ضمن القائمة.',
        'form_sys_allow_user_theme_override': 'السماح للمستخدم بتغيير المظهر',
        'help_sys_allow_user_theme_override': 'السماح للمستخدمين بالتبديل بين المظاهر المسموح بها من صفحة الخيارات ومن شريط أدوات الشريط الجانبي.',
        'form_sys_allowed_fonts': 'الخطوط المسموح بها',
        'help_sys_allowed_fonts': 'اختر الخطوط المتاحة للاستخدام في هذا المشروع. يجب أن تبقى الخطوط الافتراضية لكل لغة مفعلة.',
        'form_sys_allow_user_font_override': 'السماح للمستخدم بتغيير الخط',
        'help_sys_allow_user_font_override': 'السماح للمستخدمين بالتبديل بين الخطوط المسموح بها من صفحة الخيارات.',
        'form_sys_default_fonts': 'الخطوط الافتراضية حسب اللغة',
        'form_sys_allow_user_language_override': 'السماح للمستخدم بتغيير اللغة',
        'help_sys_allow_user_language_override': 'السماح للمستخدمين باختيار لغة العرض من صفحة الخيارات. عند التعطيل سيتم فرض اللغة الافتراضية للنظام.',
        'tables_settings_title': 'إعدادات الجداول',
        'typography_settings_title': 'إعدادات الخطوط والتخصيص',
        'default_fonts_per_lang': 'الخطوط الافتراضية حسب اللغة',
        'default_fonts_per_lang_desc': 'اختر الخط الافتراضي لكل لغة نشطة في النظام.',
        'default_font': 'الخط الافتراضي',
        'form_sys_default_table_density': 'الكثافة الافتراضية للجداول',
        'help_sys_default_table_density': 'اختر كثافة الجداول الافتراضية للمستخدمين الجدد، مع إمكانية تجاوزها لاحقاً من صفحة الخيارات.',
        'form_sys_logo': 'الشعار (Logo)',
        'form_sys_favicon': 'أيقونة الموقع (Favicon)',
        'form_sys_import_config': 'استيراد ملف إعدادات النظام',
        'help_sys_import_config': 'اختياري: اختر ملف JSON مُصدّراً من Microsys لتعبئة إعدادات التهيئة الحالية.',
        'form_sys_languages': 'اللغات المتاحة',
        'help_sys_languages': 'أضف اللغات التي تريد إتاحتها للمستخدمين.',
        'form_sys_translations': 'ترجمات الواجهة',
        'help_sys_translations': 'عدّل الترجمات من جدول المفاتيح حسب اللغة.',
        'language_catalog_add_code': 'رمز اللغة',
        'language_catalog_add_name': 'اسم العرض',
        'language_catalog_add_dir': 'الاتجاه',
        'language_catalog_add_flag': 'العلم',
        'language_catalog_suggestions': 'ملفات الترجمة تحتوي أيضاً على هذه اللغات. أضف لغة لإتاحتها للمستخدمين.',
        'translation_matrix_search': 'بحث في الترجمات',
        'translation_matrix_search_placeholder': 'مفتاح أو قيمة',
        'translation_matrix_filter': 'تصفية',
        'translation_matrix_all': 'الكل',
        'translation_matrix_missing': 'الناقصة',
        'translation_matrix_overrides': 'المعدلة',
        'translation_matrix_key': 'المفتاح',
        'translation_matrix_group_all': 'كل الأجزاء',
        'translation_matrix_group_project': 'ترجمات المشروع',
        'translation_matrix_group_runtime': 'تعديلات الإعدادات',
        'form_sys_sidebar': 'إعدادات الشريط الجانبي',
        'form_sys_sidebar_enabled': 'تفعيل الشريط الجانبي',
        'help_sys_sidebar_enabled': 'إظهار الشريط الجانبي أثناء التشغيل. عند تعطيله تتوسع مساحة المحتوى ويتم تجاهل أدوات الشريط الجانبي.',
        'form_sys_sidebar_enable_reorder': 'تفعيل إعادة ترتيب الشريط الجانبي',
        'help_sys_sidebar_enable_reorder': 'إظهار زر إعادة الترتيب السريع في شريط أدوات الشريط الجانبي حتى يتمكن المستخدم من تغيير ترتيب العناصر من الواجهة.',
        'form_sys_sidebar_enable_toolbar': 'تفعيل شريط أدوات الشريط الجانبي',
        'help_sys_sidebar_enable_toolbar': 'إظهار شريط أدوات الشريط الجانبي الذي يحتوي على مبدّل الألوان السريع وزر إعادة الترتيب واختصار مدير الأقسام الديناميكي.',
        'form_sys_sidebar_show_icons': 'إظهار أيقونات الشريط الجانبي',
        'help_sys_sidebar_show_icons': 'إظهار الأيقونات بجانب عناصر ومجلدات الشريط الجانبي عند كونه موسعاً.',
        'form_sys_sidebar_density': 'كثافة الشريط الجانبي',
        'help_sys_sidebar_density': 'اختر الكثافة الافتراضية لعناصر الشريط الجانبي.',
        'form_sys_sidebar_allow_user_density': 'السماح للمستخدم بتغيير كثافة الشريط الجانبي',
        'help_sys_sidebar_allow_user_density': 'السماح للمستخدمين بتغيير كثافة الشريط الجانبي من شريط الأدوات أثناء العمل.',
        'form_sys_sidebar_collapse_mode': 'سلوك الطي على الشاشات الكبيرة',
        'help_sys_sidebar_collapse_mode': 'اختر كيف يتصرف الشريط الجانبي عند طيه على الشاشات الكبيرة.',
        'sidebar_collapse_icons': 'أيقونات فقط',
        'sidebar_collapse_icons_desc': 'يطوي الشريط إلى مسار أيقونات على سطح المكتب.',
        'sidebar_collapse_hidden': 'إخفاء كامل',
        'sidebar_collapse_hidden_desc': 'يطوي الشريط إلى حالة مخفية بالكامل على سطح المكتب.',
        'sidebar_collapse_locked_expanded': 'يبقى موسعاً دائماً',
        'sidebar_collapse_locked_expanded_desc': 'يعطّل طي الشريط الجانبي ويُبقيه موسعاً دائماً.',
        'form_sys_titlebar_show_title': 'إظهار العنوان في الشريط',
        'help_sys_titlebar_show_title': 'إظهار اسم النظام داخل شريط العنوان.',
        'form_sys_titlebar_show_logo': 'إظهار الشعار في الشريط',
        'help_sys_titlebar_show_logo': 'إظهار شعار الهوية بجانب العنوان.',
        'form_sys_titlebar_show_home_button': 'إظهار زر الرئيسية في الشريط',
        'help_sys_titlebar_show_home_button': 'إظهار زر اختصار الرئيسية في شريط العنوان.',
        'form_sys_titlebar_home_shape': 'شكل زر الرئيسية',
        'form_sys_titlebar_title_align': 'محاذاة العنوان',
        'form_sys_titlebar_title_size': 'حجم العنوان',
        'form_sys_titlebar_height': 'ارتفاع شريط العنوان',
        'form_sys_titlebar_surface': 'سطح شريط العنوان',
        'titlebar_settings_title': 'إعدادات شريط العنوان',
        'titlebar_home_shape_circle': 'دائري',
        'titlebar_home_shape_circle_desc': 'حواف دائرية بالكامل.',
        'titlebar_home_shape_square': 'مربع',
        'titlebar_home_shape_square_desc': 'حواف مستقيمة وحادة.',
        'titlebar_home_shape_squircle': 'مربع بحواف دائرية',
        'titlebar_home_shape_squircle_desc': 'حواف ناعمة بين الدائري والمربع.',
        'titlebar_align_start': 'البداية',
        'titlebar_align_start_desc': 'ثبّت العنوان عند بداية الشريط.',
        'titlebar_align_center': 'الوسط',
        'titlebar_align_center_desc': 'اجعل العنوان في المنتصف بصرياً.',
        'titlebar_align_end': 'النهاية',
        'titlebar_align_end_desc': 'ثبّت العنوان عند نهاية الشريط.',
        'titlebar_size_sm': 'صغير',
        'titlebar_size_sm_desc': 'حجم مدمج للعنوان.',
        'titlebar_size_md': 'متوسط',
        'titlebar_size_md_desc': 'الحجم الافتراضي المتوازن.',
        'titlebar_size_lg': 'كبير',
        'titlebar_size_lg_desc': 'عنوان أكبر وأكثر بروزاً.',
        'titlebar_height_dense': 'مضغوط',
        'titlebar_height_dense_desc': 'ارتفاع أقل ومساحة رأسية أصغر.',
        'titlebar_height_balanced': 'متوازن',
        'titlebar_height_balanced_desc': 'الارتفاع الافتراضي المتوازن.',
        'titlebar_height_roomy': 'مريح',
        'titlebar_height_roomy_desc': 'مساحة داخلية أكبر لشريط العنوان.',
        'titlebar_surface_default': 'افتراضي',
        'titlebar_surface_default_desc': 'السطح الافتراضي لشريط العنوان.',
        'titlebar_surface_muted': 'هادئ',
        'titlebar_surface_muted_desc': 'سطح أقل تبايناً وأكثر هدوءاً.',
        'titlebar_surface_glass': 'زجاجي',
        'titlebar_surface_glass_desc': 'سطح زجاجي مع ضبابية خفيفة.',
        'form_sys_email_2fa': 'تفعيل التحقق الثنائي عبر البريد الإلكتروني',
        'help_sys_email_2fa': 'السماح للمستخدمين بتفعيل التحقق الثنائي عبر البريد الإلكتروني. يتطلب جاهزية إعدادات توصيل البريد في Microsys.',
        'form_sys_client_ip_mode': 'مصدر عنوان IP للعميل',
        'help_sys_client_ip_mode': 'اختر رأس الطلب الذي يجب أن يثق به Microsys عند تسجيل عناوين IP الخاصة بتسجيل الدخول والجلسات والأمان.',
        'client_ip_mode_x_forwarded_for': 'X-Forwarded-For',
        'client_ip_mode_remote_addr': 'الاتصال المباشر',
        'client_ip_mode_x_real_ip': 'X-Real-IP',
        'client_ip_mode_cloudflare': 'Cloudflare',
        'client_ip_mode_custom': 'رأس مخصص',
        'form_sys_client_ip_hops': 'عدد الوسطاء الموثوقين',
        'help_sys_client_ip_hops': 'في سلاسل X-Forwarded-For، تجاهل هذا العدد من الوسطاء الموثوقين من اليمين قبل اختيار عنوان IP الحقيقي للعميل.',
        'form_sys_client_ip_custom_header': 'اسم الرأس المخصص',
        'help_sys_client_ip_custom_header': 'اسم الرأس الذي يجب الوثوق به لاستخراج عنوان IP للعميل، مثل CF-Connecting-IP أو X-Appengine-User-Ip.',
        'client_ip_custom_header_placeholder': 'CF-Connecting-IP',
        'client_ip_settings_title': 'آلية تحديد عنوان IP للعميل',
        'client_ip_settings_desc': 'يستخدم Microsys هذا الإعداد في سجل النشاطات والأجهزة المسجّل دخولها والأجهزة الموثوقة وحدود معدل المصادقة الثنائية. أبقه بسيطاً واختر الرأس الذي يضبطه الوسيط لديك بشكل صحيح.',
        'email_delivery_settings_title': 'توصيل البريد الإلكتروني',
        'access_security_settings_title': 'الوصول والأمان',
        'email_delivery_settings_desc': 'تظهر عند تفعيل <strong>التسجيل العام</strong> أو <strong>التحقق الثنائي عبر البريد</strong>. في المشاريع المنشأة عبر <strong>python -m microsys startproject</strong> اختر <strong>مرحّل SMTP الداخلي</strong>: الويب وCelery يتصلان فقط بـ <strong>smtp-relay:1025</strong> <strong>بدون TLS/SSL</strong>، وحقول مزود SMTP أدناه يستخدمها المرحّل للاتصال الخارجي. اختر <strong>SMTP مباشر</strong> فقط إذا كانت خدمة الويب تستطيع الوصول إلى مزود البريد مباشرة. استخدم <strong>سر قاعدة البيانات المشفرة</strong> لكلمات المرور المُدارة من الواجهة؛ التصدير يبقى محجوباً.',
        'form_sys_email_transport': 'مسار التوصيل',
        'form_sys_email_secret_storage': 'تخزين السر',
        'form_sys_email_host': 'مضيف مزود SMTP',
        'form_sys_email_port': 'منفذ مزود SMTP',
        'form_sys_email_use_tls': 'STARTTLS للمزود',
        'form_sys_email_use_ssl': 'SSL للمزود',
        'form_sys_email_username': 'اسم مستخدم مزود SMTP',
        'form_sys_email_password': 'كلمة مرور مزود SMTP',
        'form_sys_email_default_from': 'بريد المرسل الافتراضي',
        'form_sys_public_root': 'السماح بالوصول العام للصفحة الرئيسية',
        'help_sys_public_root': 'السماح للمستخدمين غير المسجلين بالدخول بالوصول إلى الرابط الرئيسي (/). عند التفعيل، لن يتم فرض التحويل إلى صفحة تسجيل الدخول.',
        'form_sys_public_registration': 'تفعيل التسجيل العام',
        'help_sys_public_registration': 'السماح للمستخدمين غير المسجلين بطلب إنشاء حساب. يتطلب التحقق من البريد الإلكتروني وتجهيز إعدادات توصيل البريد.',
        'form_sys_public_root_split_enabled': 'فصل الجذر العام للمستخدم غير المسجّل عن رابط الصفحة الرئيسية',
        'help_sys_public_root_split_enabled': 'عند التفعيل، يمكن توجيه المستخدمين غير المسجّلين إلى رابط جذر عام منفصل بينما يستمر المستخدمون المسجّلون في استخدام رابط الصفحة الرئيسية الأساسي.',
        'root_home_settings_title': 'وجهات الصفحة الرئيسية والجذر العام',
        'form_sys_titlebar_hide_on_public_unauthenticated_index': 'إخفاء الشريط في الصفحة العامة للمستخدم غير المسجّل',
        'help_sys_titlebar_hide_on_public_unauthenticated_index': 'إخفاء الشريط العلوي لأي مستخدم غير مسجّل في الصفحة الرئيسية العامة.',
        'sidebar_disabled_navigation_note': 'تعطيل الشريط الجانبي قد يجعل التطبيق بلا تنقل مدمج. ستحتاج إلى الاعتماد على لوحات المعلومات والنوافذ المنبثقة، أو إضافة أزرار رجوع وروابط تنقل مخصصة داخل النماذج والقوائم ولوحات المعلومات. ابتداءً من v2.2.0، مدير الأقسام الديناميكي متاح فقط من خلال الشريط الجانبي، لذلك أضف له زراً في لوحة معلومات أو مدخلاً مخصصاً إذا كنت تحتاج الوصول إليه. سيتم تحديث هذا التحذير مستقبلاً إذا تمت إضافة بديل مدمج.',
        'sidebar_toolbar_disable_note': 'تعطيل شريط أدوات الشريط الجانبي يزيل أيضاً الاختصار المدمج الوحيد لمدير الأقسام الديناميكي. إذا كنت لا تزال تريد الوصول إليه من الواجهة، فعّل عناصر النظام داخل منشئ الشريط الجانبي ثم أضف إدارة الأقسام إلى الشريط الجانبي.',
        'btn_save': 'حفظ التعديلات',
        'sidebar_selected_title': 'الشريط المختار',
        'sidebar_selected_desc': 'ابنِ العناصر العلوية والمجموعات القابلة للطي هنا.',
        'sidebar_available_title': 'العناصر المكتشفة',
        'sidebar_available_desc': 'هذه المسارات صالحة للملاحة ويمكن إضافتها للشريط الجانبي.',
        'sidebar_add_group': 'إضافة مجموعة',
        'sidebar_add_entry': 'إضافة',
        'sidebar_add_all': 'إضافة الكل',
        'sidebar_remove_entry': 'إزالة',
        'sidebar_remove_all': 'إزالة الكل',
        'sidebar_move_root': 'نقل إلى الجذر',
        'sidebar_home_title': 'رابط الصفحة الرئيسية',
        'sidebar_home_desc': 'اختياري: اختر عنصراً علوياً فقط إذا أردت أن يشير زر الرئيسية في الشريط العلوي إليه.',
        'sidebar_inspector_title': 'لوحة التحرير',
        'sidebar_inspector_desc': 'عدّل اسم العنصر وأيقونته مباشرة من نفس الصفحة.',
        'sidebar_inspector_empty': 'حدّد عنصراً أو مجموعة من الجهة اليسرى لبدء التحرير.',
        'sidebar_label_field': 'الاسم الظاهر',
        'sidebar_icon_field': 'الأيقونة',
        'sidebar_duplicate': 'نسخ',
        'sidebar_group_label': 'مجموعة',
        'sidebar_new_group': 'مجموعة جديدة',
        'sidebar_copy_suffix': 'نسخة',
        'sidebar_no_home_items': 'استخدم رابط زر الرئيسية الافتراضي في الشريط العلوي.',
        'sidebar_home_use_default': 'استخدم رابط زر الرئيسية الافتراضي في الشريط العلوي',
        'sidebar_no_available': 'لا توجد عناصر متاحة تطابق البحث أو الاختيار الحالي.',
        'sidebar_no_selected': 'لم يتم اختيار أي عناصر بعد.',
        'sidebar_show_system_items': 'إظهار عناصر النظام',
        'sidebar_sections_manager_tooltip': 'مدير الأقسام الديناميكي',
        'enable_scopes': 'تفعيل النطاقات',
        'enable_auto_scopes': 'عزل المستخدمين تلقائياً (إنشاء نطاق لكل مستخدم)',

        # Options page
        'options_title': 'خيارات التطبيق',
        'accessibility': 'سهولة الوصول',
        'accessibility_desc': 'تخصيص العرض لمساعدة ذوي الإعاقة البصرية أو عمى الألوان.',
        'high_contrast': 'تباين عالي (High Contrast)',
        'grayscale': 'تدرج رمادي (Grayscale)',
        'invert': 'عكس الألوان (Invert)',
        'large_text': 'تكبير العرض (150%)',
        'no_animations': 'الحد من التحركات (Disable Animations)',
        'system_info': 'معلومات النظام',
        'server_time': 'وقت الخادم (Backend)',
        'memory': 'الذاكرة (Memory)',
        'storage': 'التخزين (Storage)',
        'os_info': 'نظام التشغيل (OS)',
        'python_version': 'نسخة Python',
        'django_version': 'نسخة Django',
        'decrypter_version': 'نسخة Decrypter',
        'drf_version': 'نسخة DRF',
        'api_status': 'حالة الـ API',
        'api_online': 'متاح (Online)',
        'api_offline': 'غير متاح (Offline)',
        'status_online': 'متاح',
        'status_offline': 'غير متاح',
        'status_degraded': 'تحذير',
        'status_configured': 'مهيأ',
        'service_error_detail': 'الخطأ: {error}',
        'service_db_version_lookup_failed': 'تم الاتصال، لكن تعذر جلب نسخة قاعدة البيانات: {error}',
        'service_cache_probe_unexpected': 'استجابت خدمة التخزين المؤقت، لكن نتيجة فحص السلامة كانت غير متوقعة.',
        'service_api_http_status': 'استجابت الواجهة البرمجية برمز HTTP {status}.',
        'service_celery_missing_package': 'تم اكتشاف إعدادات Celery، لكن الحزمة نفسها غير مثبتة.',
        'service_celery_configured': 'تم اكتشاف إعدادات Celery، لكن لا يتم فحص حالة الـ worker تلقائياً من هنا.',
        'database': 'قاعدة البيانات (Database)',
        'cache': 'التخزين المؤقت (Cache)',
        'tasks': 'خادم المهام (Tasks)',
        'microsys_version': 'إصدار النظام (microSYS)',
        'themes': 'سمة الألوان',
        'themes_desc': 'اختر مظهر الألوان المفضل لديك لواجهة المنظومة.',
        'typography': 'الخطوط والطباعة',
        'typography_desc': 'اختر الخط المفضل لديك لواجهة المنظومة.',
        'table_density': 'كثافة الجداول',
        'table_density_desc': 'تحكم في مقدار المساحة الرأسية التي تستخدمها الجداول أثناء العمل.',
        'sidebar_density': 'كثافة الشريط الجانبي',
        'sidebar_density_desc': 'تحكم في مقدار المساحة الرأسية التي يستخدمها الشريط الجانبي أثناء العمل.',
        'table_density_balanced': 'متوازن',
        'table_density_balanced_desc': 'الوضع الافتراضي المريح لمعظم شاشات الإدارة.',
        'table_density_dense': 'مضغوط',
        'table_density_dense_desc': 'يعرض عدداً أكبر من السجلات على الشاشة بمسافات أقل.',
        'table_density_roomy': 'مريح',
        'table_density_roomy_desc': 'صفوف أكبر ومسافات أوسع لقراءة أسهل.',
        'sidebar_density_balanced_desc': 'التوازن الافتراضي بين الكثافة وسهولة القراءة.',
        'sidebar_density_dense_desc': 'صفوف ومسافات أكثر تقارباً لإظهار عناصر أكثر في الشريط الجانبي.',
        'sidebar_density_roomy_desc': 'ارتفاعات ومسافات أكبر لواجهة تنقل أكثر راحة.',
        'table_empty_title': 'لا توجد سجلات',
        'table_empty_desc': 'لا توجد بيانات مطابقة لعرضها حالياً.',
        'table_rows_per_page': 'عدد الصفوف',
        'table_total_records': 'إجمالي السجلات',
        'table_page_label': 'الصفحة',
        'table_of_label': 'من',
        'theme_white': 'أبيض',
        'theme_royal': 'ملكي',
        'theme_gold': 'ذهبي',
        'theme_green': 'أخضر',
        'theme_red': 'أحمر',
        'theme_mono': 'مونو',
        'theme_dark': 'ليلي',
        'theme_gothic': 'غوثيك',
        'theme_retro': 'ريترو',
        'autofill': 'التعبئة التلقائية',
        'autofill_desc': 'تفعيل تعبئة البيانات تلقائياً من آخر خيار تم إدخاله (تاريخ, رقم, ...).',
        'on_off': 'تشغيل / إيقاف',
        'reset_defaults': 'استعادة الافتراضيات',
        'reset_desc': 'إعادة تعيين كافة تفضيلات المستخدم إلى الوضع الافتراضي (المظهر، اللغة، الخ).',
        'reset_btn': 'إعادة التعيين الآن',
        'reset_success': 'تمت استعادة الافتراضيات بنجاح.',
        'reset_confirm': 'هل أنت متأكد من رغبتك في استعادة كافة الإعدادات الافتراضية؟ سيتم تحديث الصفحة.',
        'language': 'اللغة',
        'language_desc': 'اختر لغة العرض المفضلة.',

        # Autofill toast
        'autofill_enabled': 'تم تفعيل التعبئة التلقائية.',
        'autofill_disabled': 'تم إيقاف التعبئة التلقائية.',

        # Auth / Admin verbose names (used by apps.py)
        'auth_system': 'نظام المصادقة',
        'permission_manage': 'ادارة الصلاحيات',
        'permissions': 'الصلاحيات',

        # Sidebar system group
        'sidebar_system': 'إدارة النظام',

        # Table headers (used by tables.py)
        'tbl_username': 'اسم المستخدم',
        'tbl_phone': 'رقم الهاتف',
        'tbl_email': 'البريد الالكتروني',
        'tbl_scope': 'النطاق',
        'tbl_full_name': 'الاسم الكامل',
        'tbl_is_staff': 'مسؤول',
        'tbl_is_active': 'نشط',
        'tbl_last_login': 'اخر دخول',
        'tbl_timestamp': 'وقت العملية',
        'tbl_model_name': 'النموذج',
        'tbl_action': 'الإجراء',
        'tbl_object_id': 'رقم العنصر',
        'tbl_number': 'الهدف',
        'tbl_name': 'الاسم',
        'tbl_created_by': 'أنشئ بواسطة',
        'tbl_created_at': 'أنشئ في',
        'tbl_scope_default': 'عام',

        # Filter placeholders
        'label_keyword': 'بحث...',
        # 'filter_search': 'البحث',
        'filter_year': 'السنة',
        'filter_date': 'التاريخ',
        'filter_date_from': 'من تاريخ',
        'filter_date_to': 'إلى تاريخ',
        'filter_scope': 'النطاق',
        'filter_all': 'الكل',
        'filter_from': 'من ',
        'filter_to': 'إلى ',

        # Template strings (manage_users)
        'add_user': 'إضافة مستخدم جديد',
        'manage_scopes_btn': 'إدارة النطاقات',
        'enable_scopes': 'تفعيل النطاقات',
        'confirm_delete': 'تأكيد الحذف',
        'delete_user_msg': 'هل انت متأكد انك تريد حذف المستخدم',
        'yes_delete': 'نعم، احذف',
        'cancel': 'إلغاء',
        'confirm': 'تأكيد',
        'loading': 'جاري التحميل...',
        'scope_warning_title': 'تحذير هام',
        'scope_warning_msg': 'هل أنت متأكد من رغبتك في تفعيل نظام النطاقات؟',
        'scope_warning_detail': 'تنبيه: بعد تفعيل النظام وتعيين المستخدمين لنطاقات محددة، لن تتمكن من تعطيله لاحقاً دون المخاطرة بفقدان بيانات هيكلية المستخدمين أو تعطل الصلاحيات، او فقدان امكانية الوصول الى البيانات الموجودة على التطبيق.',
        'scope_warning_note': 'لا يمكن تفعيل او الغاء تفعيل هذه الميزة الا بواسطة مدير النظام (Superuser).',
        'yes_activate': 'نعم، قم بالتفعيل',
        'cannot_disable_scopes': 'لا يمكن التعطيل لوجود مستخدمين مرتبطين بنطاقات',

        # Template strings (sections)
        'manage_label': 'إدارة',
        'list_label': 'قائمة',
        'save': 'حفظ',
        'add_label': 'إضافة',
        'edit_label': 'تعديل',
        'edit_user_label': 'تعديل المستخدم',
        'edit_permissions_label': 'تعديل الصلاحيات',
        'delete_label': 'حذف',
        'subsections': 'الأقسام الفرعية',
        'subsection_help_tooltip': 'للتعديل أو الحذف: اضغط بزر الفأرة الأيمن على القسم، أو اضغط مطولاً على الهاتف',
        'subsection_empty': 'لا توجد أقسام فرعية',
        'subsection_locked_tooltip': 'لا يمكن حذف هذا العنصر لارتباطه بملفات',
        'error_generic': 'حدث خطأ ما!',
        'no_models': 'لا توجد موديلات متاحة.',
        'model_load_error': 'هناك خطأ في تحميل المودل.',
        'view_label': 'عرض',
        'delete_error_related': 'لا يمكن الحذف لارتباطه بسجلات أخرى.',

        # Activity log page
        # Activity log page
        'log_title': 'سجل النشاط',
        'no_items': 'لا توجد عناصر',
        'select_all': 'تحديد الكل',
        'unit_items': 'وحدة',

        # Apps & Models (Permissions / Sidebar)
        'app_microsys': 'إدارة النظام',
        'app_auth': 'نظام المصادقة',
        'app_admin': 'لوحة التحكم',
        'app_sessions': 'الجلسات',
        'app_contenttypes': 'أنواع المحتوى',
        'model_user': 'المستخدمين',
        'model_group': 'المجموعات',
        'model_permission': 'الصلاحيات',
        'model_scope': 'النطاقات',
        'model_log': 'سجل النشاط',
        'model_scope_settings': 'إعدادات النطاق',
        'model_systemsettings': 'إعدادات النظام',
        'model_system_settings': 'إعدادات النظام',
        'model_section': 'الأقسام',
        'model_subsection': 'الأقسام الفرعية',
        'model_profile': 'ملف المستخدم',
        'model_useractivitylog': 'سجل النشاط',
        'model_password': 'كلمة المرور',
        'model_user profile': 'بيانات المستخدم',
        'model_auth': 'المصادقة',

        # Theme picker
        'theme_pick_color': 'اختر اللون',
        'theme_change': 'تغيير المظهر',
        'sidebar_density_runtime': 'كثافة الشريط الجانبي',
        'theme_light': 'أبيض',
        'theme_blue': 'ملكي',
        'theme_gold': 'ذهبي',
        'theme_green': 'أخضر',
        'theme_red': 'أحمر',
        'theme_mono': 'مونو',
        'theme_dark': 'ليلي',
        'theme_gothic': 'غوثيك',
        'theme_retro': 'ريترو',
        'theme_neon': 'نيون',
        'sidebar_reorder': 'إعادة الترتيب',

        # User form Labels
        'user_label': 'مستخدم',
        'reset_password': 'إعادة تعيين كلمة المرور',
        'form_username': 'اسم المستخدم',
        'form_password': 'كلمة المرور',
        'form_password_confirm': 'تأكيد كلمة المرور',
        'form_firstname': 'الاسم الأول',
        'form_lastname': 'اللقب',
        'form_email': 'البريد الإلكتروني',
        'form_phone': 'رقم الهاتف',
        'form_scope': 'النطاق',
        'form_permissions': 'الصلاحيات',
        'form_is_staff': 'تفعيل صلاحيات المستخدم الإداري',
        'form_is_active': 'تفعيل الحساب',
        'form_profile_pic': 'الصورة الشخصية',
        'form_new_password': 'كلمة المرور الجديدة',
        'form_confirm_new_password': 'تأكيد كلمة المرور الجديدة',
        'form_old_password': 'كلمة المرور القديمة',
        'form_scope_name': 'اسم النطاق',
        
        # User form Help Text
        'help_username': 'اسم المستخدم يجب أن يكون فريدًا، 20 حرفًا أو أقل. فقط حروف، أرقام و @ . + - _',
        'help_email': 'أدخل عنوان البريد الإلكتروني الصحيح (اختياري)',
        'help_phone': 'أدخل رقم الهاتف الصحيح (اختياري)',
        'help_password_common': """
        <ul class="mb-0 ps-3"><li>كلمة المرور يجب ألا تكون مشابهة لمعلوماتك الشخصية.</li>
        <li>كلمة المرور يجب ان تحتوي على 8 حروف وارقام على الاقل.</li>
        <li>كلمة المرور يجب الا تكون شائعة والا تكون رقمية بالكامل.</li></ul>
        """,
        'help_password_match': 'أدخل نفس كلمة المرور مجددا للتحقق.',
        'help_is_active': 'يحدد ما إذا كان يجب اعتبار هذا الحساب نشطًا. قم بإلغاء تحديد هذا الخيار بدلاً من الحذف.',
        'help_is_staff': 'يُفعّل صلاحيات المستخدم الإداري. الدرجة النهائية تعتمد على النطاق والصلاحيات المحددة.',
        'help_is_staff_no_perm': 'ليس لديك صلاحية لتعيين هذا المستخدم كمسؤول.',
        'help_scope_self': 'لا يمكنك تغيير نطاقك الخاص لمنع تجريد نفسك من صلاحيات المدير العام.',
        
        # Buttons
        'btn_add': 'إضافة',
        'enable': 'تفعيل',
        'btn_update': 'تحديث',
        'btn_cancel': 'إلغاء',
        'btn_next': 'التالي',
        'btn_prev': 'السابق',
        'btn_change_password': 'تغيير كلمة المرور',
        
        # Permissions UI
        'can_add': 'إضافة',
        'can_change': 'تعديل',
        'can_delete': 'حذف',
        'can_view': 'عرض',
        'permission_word': 'الصلاحيات',
        'perm_staff_access': 'درجة وصلاحيات المستخدم الإداري',
        'perm_manage_users': 'إدارة المستخدمين',
        'perm_view_sections': 'عرض الأقسام',
        'perm_manage_sections': 'إدارة الأقسام',
        'perm_manage_scopes': 'صلاحيات المسؤول العام',
        'help_perm_manage_scopes': 'تمنح درجة المسؤول العام فقط عندما لا يكون للمستخدم نطاق معيّن.',
        'perm_manage_staff': 'يمكنه تعيين درجات المستخدمين الإداريين',
        'help_perm_manage_staff': 'يسمح لهذا المستخدم الإداري بتعيين صلاحيات الإدارة للآخرين دون توسيع نطاقه الخاص.',
        'perm_view_activity_log': 'عرض سجل النشاط',
        'perm_view_activitylog': 'عرض سجل النشاط',
        'staff_tier_preview': 'معاينة درجة الإدارة',
        'staff_tier_preview_caption': 'ملخص للقراءة فقط يعتمد على صلاحيات الإدارة والنطاق والصلاحيات المحددة.',
        'tier_regular_user': 'مستخدم عادي',
        'tier_desc_regular_user': 'لا توجد صلاحيات لإدارة المستخدمين مفعلة لهذا الحساب.',
        'tier_superuser': 'مدير النظام',
        'tier_desc_superuser': 'وصول كامل لإدارة النظام والمستخدمين دون قيود نطاق أو صلاحيات.',
        'tier_global_staff': 'مسؤول عام',
        'tier_desc_global_staff': 'صلاحيات إدارية عبر جميع النطاقات مع إمكانية إدارة النطاقات.',
        'tier_central_staff': 'مسؤول مركزي',
        'tier_desc_central_staff': 'صلاحيات إدارية محصورة بالمستخدمين بدون نطاق داخل النظام المركزي.',
        'tier_scoped_staff': 'مسؤول نطاق',
        'tier_desc_scoped_staff': 'صلاحيات إدارية محصورة داخل النطاق المعيّن فقط.',
        'tier_delegate_badge': 'يمكنه تعيين درجات الإدارة',
        'tier_warning_needs_staff': 'تم تحديد صلاحيات إدارية، لكن تفعيل المستخدم الإداري غير مفعل بعد.',
        'tier_warning_scoped_manage_scopes': 'صلاحية المسؤول العام لا تكون فعالة أثناء وجود نطاق معيّن.',
        'tier_cap_regular_1': 'لا يمكنه الوصول إلى دليل المستخدمين الإداري.',
        'tier_cap_regular_2': 'يمكنه استخدام ميزات الحساب العادية فقط.',
        'tier_cap_regular_3': 'صلاحيات الإدارة تبقى غير فعالة حتى يتم تفعيل المستخدم الإداري.',
        'tier_cap_superuser_1': 'يمكنه عرض وإدارة جميع المستخدمين والنطاقات.',
        'tier_cap_superuser_2': 'يمكنه تعيين أي درجة إدارية أو أي صلاحية.',
        'tier_cap_superuser_3': 'يمكنه الوصول إلى جميع أدوات إدارة النظام.',
        'tier_cap_global_1': 'يمكنه عرض وإدارة المستخدمين عبر جميع النطاقات.',
        'tier_cap_global_2': 'يمكنه إنشاء النطاقات وإدارتها.',
        'tier_cap_global_3': 'يمكنه تعيين المستخدمين لأي نطاق أو تركهم بدون نطاق.',
        'tier_cap_central_1': 'يمكنه إدارة المستخدمين بدون نطاق فقط.',
        'tier_cap_central_2': 'لا يمكنه رؤية المستخدمين ذوي النطاق أو بياناتهم.',
        'tier_cap_central_3': 'لا يمكنه تعيين نطاقات أو إدارة النطاقات.',
        'tier_cap_scoped_1': 'يمكنه إدارة المستخدمين داخل النطاق المعيّن فقط.',
        'tier_cap_scoped_2': 'لا يمكنه الوصول إلى المستخدمين خارج نطاقه.',
        'tier_cap_scoped_3': 'تعيين النطاق يحدد الرؤية وإجراءات إدارة المستخدمين.',

        # Activity Log Actions
        'action_login': 'تسجيل دخول',
        'action_logout': 'تسجيل خروج',
        'action_create': 'إنشاء',
        'action_update': 'تحديث',
        'action_delete': 'حذف',
        'action_view': 'عرض',
        'action_download': 'تحميل',
        'action_confirm': 'تأكيد',
        'action_reject': 'رفض',
        'action_reset': 'إعادة تعيين',
        
        # Activity Log Modal
        'view_details': 'عرض التفاصيل',
        'activity_details': 'تفاصيل النشاط',
        'label_related_object': 'الكائن المرتبط',
        'label_changes': 'التغييرات / التفاصيل',
        'label_previous_value': 'القيمة السابقة',
        'label_new_value': 'القيمة الجديدة',
        'label_value': 'القيمة',
        'label_file': 'الملف',
        'label_count': 'العدد',
        'label_download': 'تحميل',
        'label_items': 'عنصر',
        'log_change_set': 'تم التعيين',
        'log_change_cleared': 'تم المسح',
        'log_change_changed': 'تم التغيير',
        'log_change_info': 'معلومة',
        'log_value_empty': 'فارغ',
        'no_details': 'لا توجد تفاصيل مسجلة.',
        'btn_close': 'إغلاق',

        # Profile
        'role_superuser': 'مدير النظام',
        'role_staff': 'مستخدم مسؤول',
        'role_user': 'مستخدم عادي',
        'btn_update_data': 'تحديث البيانات',
        'btn_home': 'الرئيسية',
        'btn_confirm_password_change': 'تأكيد تغيير كلمة المرور',
        'profile_update_title': 'تحديث الملف الشخصي',
        'save_changes': 'حفظ التغييرات',
        'profile_picture': 'صورة الملف الشخصي',
        'signed_in_devices': 'الأجهزة المسجّل دخولها',
        'signed_in_devices_desc': 'راجع جلسات المتصفح النشطة وقم بتسجيل الخروج من الأجهزة التي لم تعد تستخدمها.',
        'active_sessions': 'نشطة',
        'current_session': 'الجلسة الحالية',
        'trusted_device_badge': 'جهاز موثوق',
        'trusted_until': 'موثوق حتى',
        'session_expires': 'تنتهي في',
        'current': 'الحالي',
        'no_active_sessions': 'لم يتم العثور على جلسات نشطة.',
        
        # Messages
        'msg_password_changed': 'تم تغيير كلمة المرور بنجاح!',
        'msg_form_error': 'هناك خطأ في البيانات المدخلة',

        # User Detail View
        'user_details_title': 'تفاصيل مستخدم',
        'user_details_header': 'تفاصيل المستخدم',
        'account_active': 'فعال',
        'account_inactive': 'معطل',
        'account_active_tooltip': 'حساب مفعل',
        'account_inactive_tooltip': 'حساب معطل',
        'staff_permissions_tooltip': 'لديه صلاحيات إدارية',
        'role_type': 'نوع الصلاحيات',
        'date_joined': 'تاريخ الانضمام',
        'back_to_users': 'العودة إلى إدارة المستخدمين',
        'tbl_staff_tier': 'درجة الإدارة',

        # Profile Enhancements
        'stats_total_actions': 'إجمالي العمليات',
        'stats_docs_created': 'ادخالات جديدة',
        'stats_edits': 'التعديلات',
        'stats_downloads': 'التنزيلات',
        'stats_recent_activity': 'آخر النشاطات',
        'stats_system_interactions': 'تفاعلات النظام',
        'profile_completeness': 'اكتمال الملف الشخصي',
        'account_health': 'حالة الحساب',
        'account_health_good': 'جيد',
        'account_health_attention': 'يحتاج انتباه',
        'badge_verified': 'موثق',
        'badge_admin': 'مدير النظام',
        'badge_staff': 'مسؤول',
        'timeline_empty': 'لا يوجد نشاط حديث',

        # 2FA
        '2fa_title': 'المصادقة الثنائية',
        '2fa_desc': 'قم بتأمين حسابك باستخدام رمز تحقق من هاتفك الخاص او بريدك الالكتروني.',
        '2fa_enable': 'تفعيل المصادقة الثنائية',
        '2fa_disable': 'تعطيل المصادقة الثنائية',
        '2fa_enabled_msg': 'تم تفعيل المصادقة الثنائية بنجاح.',
        '2fa_disabled_msg': 'تم تعطيل المصادقة الثنائية.',
        '2fa_verify_title': 'تحقق من هويتك',
        '2fa_verify_desc': 'لقد أرسلنا رمز تحقق إلى بريدك الإلكتروني. الرجاء إدخاله أدناه.',
        'totp_scan_instruction': 'قم بمسح رمز QR هذا باستخدام تطبيق المصادقة الخاص بك (مثلاً Google Authenticator أو Authy).',
        'otp_sent_instruction': 'أدخل الرمز المرسل إلى',
        '2fa_code': 'رمز التحقق',
        '2fa_verify_btn': 'تحقق',
        '2fa_resend_btn': 'إعادة إرسال الرمز',
        '2fa_code_sent': 'تم إرسال رمز جديد إلى بريدك الإلكتروني.',
        '2fa_invalid_code': 'رمز غير صحيح أو منتهي الصلاحية.',
        '2fa_setup_email_subject': 'رمز تفعيل المصادقة الثنائية - microsys',
        '2fa_login_email_subject': 'رمز الدخول - microsys',
        '2fa_email_body': 'رمز التحقق الخاص بك هو: {code}. صلاحية الرمز 5 دقائق.',
        '2fa_method_backup': 'رموز الاسترداد',
        'backup_codes_title': 'رموز الاسترداد الاحتياطية',
        'backup_codes_desc': 'احتفظ بهذه الرموز في مكان آمن. يمكنك استخدامها لتسجيل الدخول في حال فقدان طرق المصادقة الاخرى.',
        'btn_view_generate': 'عرض / إنشاء',
        'btn_download_txt': 'تحميل كملف نصي',
        'btn_close': 'إغلاق',
        '2fa_backup_instruction': 'أدخل أحد رموز الاسترداد المكون من 8 أرقام.',
        '2fa_enabled_success': 'تم تفعيل المصادقة الثنائية بنجاح!',
        'backup_codes_warning': '<strong>تنبيه:</strong> سيتم عرض رموز الاسترداد هذه <strong>مرة واحدة فقط</strong>. احفظها فوراً.',
        'btn_close_reload': 'لقد حفظت الرموز',
        '2fa_method_email': 'المصادقة عبر البريد الإلكتروني',
        '2fa_method_phone': 'المصادقة عبر الهاتف (SMS)',
        '2fa_method_totp': 'تطبيق المصادقة (Authenticator App)',
        '2fa_confirm_email_title': 'تأكيد بريد المصادقة الثنائية',
        '2fa_confirm_email_instruction': 'أكد أو حدّث عنوان البريد قبل أن نرسل رمز الإعداد.',
        '2fa_confirm_email_label': 'عنوان البريد للمصادقة الثنائية',
        '2fa_confirm_email_help': 'أكد أن هذا هو عنوان البريد الذي يجب أن يستقبل رمز إعداد المصادقة الثنائية.',
        '2fa_confirm_email_send': 'إرسال رمز الإعداد',
        'btn_edit': 'تعديل',
        'btn_reset': 'إعادة تعيين',
        'modal_confirm_title': 'هل أنت متأكد؟',
        'modal_confirm_msg': 'هل تريد الاستمرار في هذا الإجراء؟',
        'msg_confirm_generate_backup': 'سيؤدي إنشاء رموز احتياطية جديدة إلى إلغاء صلاحية أي رموز سابقة. هل أنت متأكد من رغبتك في الاستمرار؟',
        'msg_confirm_disable_2fa': 'هل أنت متأكد من رغبتك في تعطيل المصادقة الثنائية لهذه الطريقة؟',
        'msg_confirm_sign_out_session': 'هل أنت متأكد من رغبتك في إنهاء جلسة هذا الجهاز؟',
        'current_password_prompt': 'يرجى إدخال كلمة المرور الحالية للمتابعة.',
        'current_password_required': 'يرجى إدخال كلمة المرور الحالية.',
        'current_password_incorrect': 'كلمة المرور الحالية غير صحيحة.',
        'status_enabled': 'مفعل',
        'btn_generate_new': 'إنشاء رموز جديدة',
        'duration_minute': 'دقيقة',
        'duration_minutes': 'دقائق',
        'duration_hour': 'ساعة',
        'duration_hours': 'ساعات',
        'duration_day': 'يوم',
        'duration_days': 'أيام',
        'duration_week': 'أسبوع',
        'duration_weeks': 'أسابيع',
        'duration_month': 'شهر',
        'duration_months': 'شهور',
        'duration_and': 'و',
        'ago': 'منذ',
        'no_activity_recorded': 'لم يتم تسجيل نشاط بعد.',

        # Tutorial / Guided Tour
        'tut_btn_next': 'التالي',
        'tut_btn_prev': 'السابق',
        'tut_btn_skip': 'إلغاء',
        'tut_btn_finish': 'إنهاء',
        'tut_of': 'من',
        
        # Dashboard Tutorial
        'tut_sidebar_title': 'القائمة الجانبية',
        'tut_sidebar_desc': 'يمكنك التنقل بين أقسام النظام المختلفة من هنا في اي وقت.',
        'tut_titlebar_title': 'شريط العنوان',
        'tut_titlebar_desc': 'يحتوي على اسم النظام والقائمة الشخصية للمستخدم.',
        'tut_usermenu_title': 'قائمة المستخدم',
        'tut_usermenu_desc': 'من هنا يمكنك تسجيل الخروج أو الذهاب لصفحة الملف الشخصي.',
        'tut_maincontent_title': 'منطقة العمل',
        'tut_maincontent_desc': 'هنا تظهر الجداول، النماذج، والمحتوى الرئيسي للنظام.',
        
        # Lists / Tables Tutorial
        'tut_search_title': 'البحث السريع',
        'tut_search_desc': 'ابحث عن السجلات باستخدام العناوين، الكلمات المفتاحية، أو الأرقام.',
        'tut_add_title': 'إضافة جديد',
        'tut_add_desc': 'اضغط هنا لإضافة سجل أو عنصر جديد لهذا القسم.',
        'tut_table_title': 'جدول البيانات',
        'tut_table_desc': 'هنا يتم عرض السجلات. يمكنك الضغط على العناصر للعرض أو التعديل.',
        
        # Sections Tutorial
        'tut_sections_list_title': 'قائمة الأقسام',
        'tut_sections_list_desc': 'تعرض هذه القائمة جميع الأقسام والجهات المعرفة في النظام.',
        
        # Users Tutorial
        'tut_users_roles_title': 'أدوار المستخدمين',
        'tut_users_roles_desc': 'يمكنك تمييز أدوار الصلاحيات من خلال العلامات (مدير، مسؤول، مستخدم).',
        'tut_users_row_title': 'تفاصيل وبدائل المستخدم',
        'tut_users_row_desc': 'انقر نقرًا مزدوجًا على أي صف لفتح بطاقة تفاصيل المستخدم شاملة سجلات نشاطه.',
        'tut_users_add_btn_title': 'إضافة مستخدم جديد',
        'tut_users_add_btn_desc': 'انقر هنا لإنشاء حساب مستخدم جديد وتحديد صلاحياته.',
        'tut_users_scopes_title': 'إدارة النطاقات',
        'tut_users_scopes_desc': 'يتيح لك نظام النطاقات تقييد رؤية المستخدمين لبيانات محددة بناءً على إداراتهم.',
        
        # Logs Tutorial
        'tut_logs_row_title': 'تفاصيل النشاط',
        'tut_logs_row_desc': 'اضغط نقراً مزدوجاً على أي صف أو اضغط على زر التفاصيل لعرض ما تم تغييره بالضبط.',
        
        # Profile Tutorial
        'tut_profile_stats_title': 'إحصائيات الملف الشخصي',
        'tut_profile_stats_desc': 'هنا تجد إحصائيات سريعة عن نشاطك داخل النظام.',
        'tut_profile_details_title': 'بياناتك الشخصية',
        'tut_profile_details_desc': 'تُعرض معلومات حسابك مثل البريد الإلكتروني ورقم الهاتف والدور في النظام هنا.',
        'tut_profile_edit_title': 'تحديث البيانات',
        'tut_profile_edit_desc': 'استخدم هذا الزر لتعديل بيانات ملفك الشخصي أو تغيير صورتك الرمزية.',
        'tut_profile_2fa_title': 'إعدادات الأمان (2FA)',
        'tut_profile_2fa_desc': 'يمكنك تفعيل وتعطيل طرق المصادقة الثنائية لزيادة أمان حسابك.',
        'tut_profile_activity_title': 'نشاطاتك الأخيرة',
        'tut_profile_activity_desc': 'يمكنك تتبع تفاعلاتك مع النظام والإجراءات الحديثة التي قمت بها هنا.',
        
        # Options Tutorial
        'tut_options_tabs_title': 'تبويبات الإعدادات',
        'tut_options_tabs_desc': 'تصفح التبويبات للوصول إلى خيارات سهولة الوصول، المظهر، والتعبئة التلقائية.',
        'tut_options_access_title': 'سهولة الوصول',
        'tut_options_access_desc': 'يتيح هذا القسم تخصيص تجربة القراءة وتفعيل خيارات مثل التباين العالي وإلغاء الحركات.',
        'tut_options_info_title': 'معلومات النظام',
        'tut_options_info_desc': 'عرض تفاصيل خادم النظام والتخزين وإصدارات الخدمات البرمجية الأساسية.',
        'tut_options_theme_title': 'المظهر والألوان',
        'tut_options_theme_desc': 'اختر المظهر الذي يناسبك، سيتم تطبيق التغييرات فوراً.',
        'tut_options_lang_title': 'إعدادات اللغة',
        'tut_options_lang_desc': 'يمكنك التبديل بين اللغات المتاحة لعرض الواجهة هنا.',
        'tut_options_autofill_title': 'التعبئة التلقائية',
        'tut_options_autofill_desc': 'عند التفعيل، سيتذكر النظام المدخلات السابقة لتسريع عملية تعبئة النماذج.',

        # Registration
        'register_title': 'تسجيل حساب جديد',
        'create_account': 'إنشاء حساب',
        'btn_register': 'تسجيل',
        'back_to_login': 'العودة لتسجيل الدخول',
        'check_email': 'تحقق من بريدك الإلكتروني',
        'registration_sent_desc': 'إذا كان العنوان مسموحاً بالتسجيل، تم إرسال رابط التحقق.',
        'account_verified': 'تم التحقق من الحساب',
        'account_active_signed_in': 'حسابك نشط وتم تسجيل دخولك.',
        'btn_continue': 'متابعة',
        'email_verified': 'تم التحقق من البريد',
        'account_pending_approval': 'حسابك بانتظار الموافقة.',
        'verification_expired': 'انتهت صلاحية التحقق',
        'verification_link_expired': 'رابط التحقق لم يعد صالحاً.',
        'register_again': 'تسجيل مرة أخرى',
        'verification_failed': 'فشل التحقق',
        'verification_link_invalid': 'رابط التحقق غير صالح أو تم استخدامه مسبقاً.',
        'btn_register_again': 'تسجيل',

        # Pending Registrations
        'pending_registrations': 'التسجيلات المعلقة',
        'tbl_email_header': 'البريد الإلكتروني',
        'tbl_name_header': 'الاسم',
        'tbl_created_header': 'تاريخ الإنشاء',
        'actions': 'الإجراءات',
        'btn_approve': 'موافقة',
        'btn_reject': 'رفض',
        'no_pending_registrations': 'لا توجد تسجيلات معلقة.',

        # 2FA Verify page extras
        '2fa_totp_or_email_instruction': 'أدخل رمز المصادقة. يمكنك طلب رمز بريد إلكتروني إذا كان مفعلًا.',
        '2fa_email_request_instruction': 'اطلب رمز بريد إلكتروني، ثم أدخله هنا.',
        '2fa_send_email_code': 'إرسال رمز بريد إلكتروني',
        '2fa_use_backup_code': 'استخدام رمز استرداد',
        '2fa_email_sent_instruction': 'تم إرسال رمز البريد الإلكتروني. أدخل الرمز المكوّن من 6 أرقام هنا.',
        '2fa_send_email_instead': 'استخدم البريد الإلكتروني بدلاً من ذلك',
        '2fa_use_authenticator': 'استخدم تطبيق المصادقة',
        '2fa_return_to_email': 'العودة إلى رمز البريد الإلكتروني',
        '2fa_return_to_authenticator': 'العودة إلى تطبيق المصادقة',
        '2fa_return_to_default': 'العودة إلى الطريقة الافتراضية',
        '2fa_email_resend_wait': 'ستتوفر إعادة الإرسال بعد {seconds}ث.',
        '2fa_trust_device_label': 'ثق بهذا الجهاز لمدة 30 يوماً',
        '2fa_invalid_email': 'أدخل عنوان بريد إلكتروني صالح.',
        '2fa_totp_prepare_failed': 'تعذر تجهيز إعداد تطبيق المصادقة. تحقق من تبعيات الخادم ثم حاول مرة أخرى.',
        '2fa_totp_generate_failed': 'تعذر إنشاء إعداد تطبيق المصادقة. حاول مرة أخرى.',

        # Dynamic Modal
        'manage_records': 'إدارة السجلات',
        'close_label': 'إغلاق',

        # Activity Log / Detail Modal
        'error_loading_details': 'خطأ في تحميل التفاصيل.',
        'label_id': 'رقم التعريف',

        # Options page extras
        'email_label': 'البريد الإلكتروني',

        # View Messages (errors & success)
        'err_no_edit_permission_account': 'ليس لديك صلاحية لتعديل هذا الحساب!',
        'err_no_edit_permission_user': 'ليس لديك صلاحية لتعديل هذا المستخدم!',
        'err_cannot_edit_global_staff': 'لا يمكن للمسؤول المركزي تعديل المستخدمين ذوي الصلاحيات العامة.',
        'err_cannot_delete_self': 'لا يمكنك حذف حسابك الخاص!',
        'err_cannot_delete_superuser': 'ليس لديك صلاحية لحذف المشرفين!',
        'err_cannot_delete_last_superuser': 'لا يمكن حذف المشرف الرئيسي الأخير للنظام!',
        'err_no_delete_permission_user': 'ليس لديك صلاحية لحذف هذا المستخدم!',
        'err_no_edit_permission_user_reset': 'ليس لديك صلاحية لتعديل هذا المستخدم!',
        'msg_registration_not_configured': 'إرسال بريد التسجيل غير مهيأ.',
        'msg_verification_email_failed': 'لم نتمكن من إرسال بريد التحقق. يرجى المحاولة لاحقاً.',
        'msg_registration_approved': 'تمت الموافقة على التسجيل.',
        'msg_registration_rejected': 'تم رفض التسجيل.',
        'err_invalid_method': 'طريقة غير صالحة.',
        'err_already_enabled': 'مفعل بالفعل.',
        'err_failed_send_otp': 'فشل في إرسال رمز التحقق.',
        'msg_code_sent': 'تم إرسال الرمز.',
        'err_unable_send_code': 'غير قادر على إرسال الرمز.',
        'err_not_authenticated': 'غير مصادق عليه.',
        'err_totp_unavailable': 'المصادقة عبر التطبيق غير متاحة.',
        'err_unable_save_totp': 'تعذر حفظ إعداد المصادقة. قم بتشغيل ترحيلات قاعدة البيانات وحاول مرة أخرى.',
        'device_unknown': 'جهاز غير معروف',
        'device_browser_generic': 'متصفح',
        'device_platform_generic': 'جهاز',
        'device_label_pattern': '{browser} على {platform}',
        'err_subsection_id_missing': 'معرف القسم الفرعي مفقود.',
        'err_subsection_not_found': 'القسم الفرعي غير موجود.',
        'msg_subsection_added': 'تم إضافة',
        'err_subsection_add_failed': 'خطأ في إضافة',
        'msg_subsection_edited': 'تم تعديل',
        'err_subsection_edit_failed': 'خطأ في تعديل',
        'err_cannot_delete_related': 'لا يمكن حذف هذا العنصر لارتباطه بسجلات أخرى.',
        'msg_subsection_deleted': 'تم حذف',
        'err_unable_update_preferences': 'تعذر تحديث التفضيلات.',
        'err_invalid_method_api': 'طريقة غير صالحة.',
        'help_is_staff_no_perm_form': 'ليس لديك صلاحية لتعيين هذا المستخدم كمسؤول.',
    },

    # ───────────────────────────── English ─────────────────────────────
    'en': {
        # Titlebar
        'help': 'Help',
        'tour_title': 'Guided Tour',
        'profile': 'Profile',
        'logout': 'Logout',
        'login': 'Login',

        # Login page
        'username': 'Username',
        'password': 'Password',
        'login_submit': 'Sign In',
        'login_logo_alt': 'Login logo',

        # Dashboard
        'dashboard_welcome': 'Welcome to the integrated resource management system.',
        'greeting_morning': 'Good Morning',
        'greeting_afternoon': 'Good Afternoon',
        'greeting_evening': 'Good Evening',
        'app_core': 'Home',
        'app_storage': 'Storage Management',
        'app_storage_desc': 'Manage assets, warehouses, and item movements.',
        'app_finance': 'Finance Management',
        'app_finance_desc': 'Manage budget, chapters, and financial transfers.',
        'app_treasury': 'Treasury',
        'app_treasury_desc': 'Manage revenues, expenses, and financial trusts.',
        'app_hr_payroll': 'HR & Payroll',
        'app_salary': 'Salary Management',
        'app_salary_desc': 'Manage salary cards, deductions, and payroll sheets.',
        'sidebar_system_desc': 'Manage users, permissions, and system settings.',
        'contact_admin': 'Please contact the system administrator to grant you access.',
        'work_scope': 'Work Scope',
        'manage_users': 'User Management',
        'manage_users_desc': 'Manage user accounts and permissions.',
        'manage_sections': 'Section Management',
        'manage_sections_desc': 'Structure departments, entities, and administrative units.',
        'activity_log': 'Activity Log',
        'activity_log_desc': 'Track user activities and changes.',
        'settings': 'Settings',
        'settings_desc': 'System options and version info.',
        'profile_desc': 'View and edit your profile details.',
        'go': 'Go',
        'activity_24h': 'Activity (Last 24 Hours)',
        'system_settings_title': 'General System Settings',
        'system_settings_label': 'System Settings',
        'system_settings_btn': 'Manage System Settings',
        'system_settings_desc': 'Configure global system settings and defaults.',
        'system_settings_export': 'Export setup file',
        'system_settings_modal_desc': 'Update branding, languages, the sidebar, and shell appearance from the settings modal.',
        'system_settings_branding': 'Branding',
        'system_settings_languages': 'Languages',
        'system_settings_security': 'Access & Security',
        'system_settings_sidebar': 'Sidebar',
        'system_settings_ui_layout': 'Titlebar',
        'system_settings_appearance': 'Themes & Typography',
        'system_setup_title': 'Initial System Setup',
        'system_setup_heading': 'Set up Microsys',
        'system_setup_desc': 'Complete branding, languages, sidebar, and appearance setup before you begin.',
        'system_setup_page_desc': 'Configure your system identity, languages, sidebar behavior, and shell appearance from one place.',
        'system_setup_step1': 'Step 1: Identity',
        'system_setup_step2': 'Step 2: Localization',
        'system_setup_step3': 'Step 3: Access & Security',
        'system_setup_step4': 'Step 4: Navigation',
        'system_setup_step5': 'Step 5: Titlebar',
        'system_setup_step6': 'Step 6: Themes & Typography',
        'apply_language': 'Apply language',

        # System Settings Form
        'form_sys_system_names': 'System Names by Language',
        'form_sys_system_name_placeholder': 'System name',
        'form_sys_home_url': 'Global Home URL',
        'help_sys_home_url': 'Choose the main Home URL. It remains the authenticated home destination and login redirect even when anonymous public-root traffic is split elsewhere.',
        'enable_scopes': 'Enable Scopes',
        'enable_auto_scopes': 'Auto User Isolation (Unique scope per user)',
        'form_sys_home_url_discovered': 'Choose From Discovered Pages',
        'help_sys_home_url_discovered': 'Optional: choose a discovered page to fill the Home URL automatically, or leave it blank and type a custom URL.',
        'form_sys_public_root_url': 'Anonymous Public Root URL',
        'help_sys_public_root_url': 'Optional: when separate public-root mode is enabled, anonymous users landing on `/` are redirected here instead of the main Home URL.',
        'form_sys_public_root_url_discovered': 'Choose Anonymous Public Root From Discovered Pages',
        'help_sys_public_root_url_discovered': 'Optional: choose a discovered page to fill the anonymous public-root destination automatically, or leave it blank and type a custom URL.',
        'form_sys_home_url_custom': 'Use a custom URL or keep the current one',
        'home_url_custom_desc': 'Keep a custom Home URL instead of pointing the titlebar button at a discovered page.',
        'selector_search_pages': 'Search discovered pages',
        'form_sys_default_lang': 'Default Language',
        'form_sys_default_theme': 'Default Theme',
        'form_sys_allowed_themes': 'Allowed themes',
        'help_sys_allowed_themes': 'Choose which themes are available in this project. The default theme must remain enabled.',
        'form_sys_allow_user_theme_override': 'Allow user theme override',
        'help_sys_allow_user_theme_override': 'Allow users to switch between the allowed themes at runtime from Options and the sidebar toolbar.',
        'form_sys_allowed_fonts': 'Allowed fonts',
        'help_sys_allowed_fonts': 'Choose which fonts are available in this project. The default fonts for each language must remain enabled.',
        'form_sys_allow_user_font_override': 'Allow user font override',
        'help_sys_allow_user_font_override': 'Allow users to switch between the allowed fonts at runtime from Options.',
        'form_sys_default_fonts': 'Default fonts by language',
        'form_sys_allow_user_language_override': 'Allow User Language Override',
        'help_sys_allow_user_language_override': 'Allow users to change their display language from Options. When disabled, the system default language is enforced.',
        'tables_settings_title': 'Tables Settings',
        'typography_settings_title': 'Typography Settings',
        'default_fonts_per_lang': 'Default Fonts by Language',
        'default_fonts_per_lang_desc': 'Choose which font to use as the default for each active language.',
        'default_font': 'Default Font',
        'form_sys_default_table_density': 'Default Table Density',
        'help_sys_default_table_density': 'Choose the default table density for new users; each user can still override it later from Options.',
        'form_sys_logo': 'System Logo (Logo)',
        'form_sys_favicon': 'Site Icon (Favicon)',
        'form_sys_import_config': 'Import system setup file',
        'help_sys_import_config': 'Optional: choose a Microsys-exported JSON setup file to populate these settings.',
        'form_sys_languages': 'Available Languages',
        'help_sys_languages': 'Add languages that should be available to users.',
        'form_sys_translations': 'Interface Translations',
        'help_sys_translations': 'Edit translations from the language-key matrix.',
        'language_catalog_add_code': 'Language Code',
        'language_catalog_add_name': 'Display Name',
        'language_catalog_add_dir': 'Direction',
        'language_catalog_add_flag': 'Flag',
        'language_catalog_suggestions': 'Translation files also contain these languages. Add one to publish it to users.',
        'translation_matrix_search': 'Search Translations',
        'translation_matrix_search_placeholder': 'Key or value',
        'translation_matrix_filter': 'Filter',
        'translation_matrix_all': 'All',
        'translation_matrix_missing': 'Missing',
        'translation_matrix_overrides': 'Overrides',
        'translation_matrix_key': 'Key',
        'translation_matrix_group_all': 'All parts',
        'translation_matrix_group_project': 'Project translations',
        'translation_matrix_group_runtime': 'Settings overrides',
        'form_sys_sidebar': 'Sidebar Configuration',
        'form_sys_sidebar_enabled': 'Enable Sidebar',
        'help_sys_sidebar_enabled': 'Show the runtime sidebar. When disabled, content expands and sidebar toolbar controls are ignored.',
        'form_sys_sidebar_enable_reorder': 'Enable sidebar reorder',
        'help_sys_sidebar_enable_reorder': 'Show the quick reorder control in the sidebar toolbar so users can rearrange sidebar items from the UI.',
        'form_sys_sidebar_enable_toolbar': 'Enable sidebar toolbar',
        'help_sys_sidebar_enable_toolbar': 'Show the sidebar toolbar that contains the quick theme picker, reorder toggle, and dynamic section manager shortcut.',
        'form_sys_sidebar_show_icons': 'Show Sidebar Icons',
        'help_sys_sidebar_show_icons': 'Show icons beside sidebar items and folders when the sidebar is expanded.',
        'form_sys_sidebar_density': 'Sidebar Density',
        'help_sys_sidebar_density': 'Choose the default density for sidebar rows.',
        'form_sys_sidebar_allow_user_density': 'Allow User Sidebar Density Override',
        'help_sys_sidebar_allow_user_density': 'Allow users to change sidebar density from the sidebar toolbar at runtime.',
        'form_sys_sidebar_collapse_mode': 'Desktop Collapse Mode',
        'help_sys_sidebar_collapse_mode': 'Choose how the sidebar behaves when collapsed on large screens.',
        'sidebar_collapse_icons': 'Icons Only',
        'sidebar_collapse_icons_desc': 'Collapse to an icon rail on desktop.',
        'sidebar_collapse_hidden': 'Hide Completely',
        'sidebar_collapse_hidden_desc': 'Collapse to a fully hidden desktop sidebar.',
        'sidebar_collapse_locked_expanded': 'Always Expanded',
        'sidebar_collapse_locked_expanded_desc': 'Disable desktop collapsing and keep the sidebar open.',
        'form_sys_titlebar_show_title': 'Show Titlebar Title',
        'help_sys_titlebar_show_title': 'Show the system title inside the titlebar.',
        'form_sys_titlebar_show_logo': 'Show Titlebar Logo',
        'help_sys_titlebar_show_logo': 'Show the configured branding logo beside the title.',
        'form_sys_titlebar_show_home_button': 'Show Titlebar Home Button',
        'help_sys_titlebar_show_home_button': 'Show the quick Home button in the titlebar.',
        'form_sys_titlebar_home_shape': 'Home Button Shape',
        'form_sys_titlebar_title_align': 'Title Alignment',
        'form_sys_titlebar_title_size': 'Title Size',
        'form_sys_titlebar_height': 'Titlebar Height',
        'form_sys_titlebar_surface': 'Titlebar Surface',
        'titlebar_settings_title': 'Titlebar Settings',
        'titlebar_home_shape_circle': 'Circle',
        'titlebar_home_shape_circle_desc': 'Fully rounded button silhouette.',
        'titlebar_home_shape_square': 'Square',
        'titlebar_home_shape_square_desc': 'Sharp square edges.',
        'titlebar_home_shape_squircle': 'Squircle',
        'titlebar_home_shape_squircle_desc': 'Soft rounded-square edges.',
        'titlebar_align_start': 'Start',
        'titlebar_align_start_desc': 'Pin the title to the start side.',
        'titlebar_align_center': 'Center',
        'titlebar_align_center_desc': 'Keep the title visually centered.',
        'titlebar_align_end': 'End',
        'titlebar_align_end_desc': 'Pin the title to the end side.',
        'titlebar_size_sm': 'Small',
        'titlebar_size_sm_desc': 'Compact title sizing.',
        'titlebar_size_md': 'Medium',
        'titlebar_size_md_desc': 'Balanced default title sizing.',
        'titlebar_size_lg': 'Large',
        'titlebar_size_lg_desc': 'Larger, more prominent title sizing.',
        'titlebar_height_dense': 'Dense',
        'titlebar_height_dense_desc': 'Tighter vertical titlebar spacing.',
        'titlebar_height_balanced': 'Balanced',
        'titlebar_height_balanced_desc': 'Default titlebar spacing.',
        'titlebar_height_roomy': 'Roomy',
        'titlebar_height_roomy_desc': 'More breathing room inside the titlebar.',
        'titlebar_surface_default': 'Default',
        'titlebar_surface_default_desc': 'Standard titlebar surface styling.',
        'titlebar_surface_muted': 'Muted',
        'titlebar_surface_muted_desc': 'Lower-contrast titlebar surface styling.',
        'titlebar_surface_glass': 'Glass',
        'titlebar_surface_glass_desc': 'Blurred glass-style titlebar surface.',
        'form_sys_email_2fa': 'Enable Email 2FA',
        'help_sys_email_2fa': 'Allow users to enable two-factor authentication via email. Requires Microsys email delivery to be ready.',
        'form_sys_client_ip_mode': 'Client IP Source',
        'help_sys_client_ip_mode': 'Choose which request header Microsys should trust when recording login, session, and security IP addresses.',
        'client_ip_mode_x_forwarded_for': 'X-Forwarded-For',
        'client_ip_mode_remote_addr': 'Direct Connection',
        'client_ip_mode_x_real_ip': 'X-Real-IP',
        'client_ip_mode_cloudflare': 'Cloudflare',
        'client_ip_mode_custom': 'Custom Header',
        'form_sys_client_ip_hops': 'Trusted Proxy Hops',
        'help_sys_client_ip_hops': 'For X-Forwarded-For chains, skip this many trusted proxies from the right before choosing the client IP.',
        'form_sys_client_ip_custom_header': 'Custom Header Name',
        'help_sys_client_ip_custom_header': 'Header name to trust for client IP resolution, such as CF-Connecting-IP or X-Appengine-User-Ip.',
        'client_ip_custom_header_placeholder': 'CF-Connecting-IP',
        'client_ip_settings_title': 'Client IP Resolution',
        'client_ip_settings_desc': 'Microsys uses this setting for activity logs, signed-in devices, trusted devices, and 2FA rate limits. Keep it simple: choose the header your proxy already sets correctly.',
        'email_delivery_settings_title': 'Email Delivery',
        'access_security_settings_title': 'Access & Security',
        'email_delivery_settings_desc': 'Visible when <strong>public signup</strong> or <strong>email 2FA</strong> is enabled. For projects created with <strong>python -m microsys startproject</strong>, choose <strong>Internal SMTP relay</strong>: web and Celery only talk to <strong>smtp-relay:1025</strong> with <strong>no TLS/SSL</strong>, and the provider fields below are loaded and used by the relay for upstream SMTP. Choose <strong>Direct SMTP</strong> only when web can reach the provider itself. Use <strong>Encrypted database secret</strong> for UI-managed passwords; exports stay redacted.',
        'form_sys_email_transport': 'Delivery path',
        'form_sys_email_secret_storage': 'Secret storage',
        'form_sys_email_host': 'Provider SMTP host',
        'form_sys_email_port': 'Provider SMTP port',
        'form_sys_email_use_tls': 'Provider STARTTLS',
        'form_sys_email_use_ssl': 'Provider SSL',
        'form_sys_email_username': 'Provider SMTP username',
        'form_sys_email_password': 'Provider SMTP password',
        'form_sys_email_default_from': 'Default from email',
        'form_sys_public_root': 'Public Root Access',
        'help_sys_public_root': 'Allow anonymous (non-logged-in) users to access the root URL (/). When enabled, the system will not force-redirect to login.',
        'form_sys_public_registration': 'Enable Public Registration',
        'help_sys_public_registration': 'Allow anonymous users to request an account. Email verification is mandatory and SMTP/email delivery must be configured.',
        'form_sys_public_root_split_enabled': 'Separate anonymous public root from Home URL',
        'help_sys_public_root_split_enabled': 'When enabled, anonymous users can be redirected to a separate Public Root URL while authenticated users still use the main Home URL.',
        'root_home_settings_title': 'Home & Public Root Destinations',
        'form_sys_titlebar_hide_on_public_unauthenticated_index': 'Hide titlebar on anonymous public home/index',
        'help_sys_titlebar_hide_on_public_unauthenticated_index': 'Hide the titlebar when an anonymous user opens the public root/home page.',
        'sidebar_disabled_navigation_note': 'Disabling the sidebar can leave the app without built-in navigation. You will need to rely on dashboards and modals, or add your own back buttons and navigation entries in forms, lists, and dashboards. As of v2.2.0, Dynamic Sections Manager is only available through the sidebar, so add a dashboard button or custom entry if you need access. This warning will be updated if a built-in workaround is added later.',
        'sidebar_toolbar_disable_note': 'Disabling the sidebar toolbar also removes the only built-in shortcut to Dynamic Sections Manager. If you still want UI access, enable system items in the sidebar builder and add Section Management to your sidebar.',
        'btn_save': 'Save Changes',
        'sidebar_selected_title': 'Selected Sidebar',
        'sidebar_selected_desc': 'Build your top-level items and accordion groups here.',
        'sidebar_available_title': 'Available Entries',
        'sidebar_available_desc': 'These routes were discovered automatically and can be added to the sidebar.',
        'sidebar_add_group': 'Add Group',
        'sidebar_add_entry': 'Add',
        'sidebar_add_all': 'Add All',
        'sidebar_remove_entry': 'Remove',
        'sidebar_remove_all': 'Remove All',
        'sidebar_move_root': 'Move To Root',
        'sidebar_home_title': 'Home Destination',
        'sidebar_home_desc': 'Optional: choose a top-level sidebar item only if you want the titlebar Home button to point there.',
        'sidebar_inspector_title': 'Inspector',
        'sidebar_inspector_desc': 'Rename the selected entry and choose its icon without leaving the page.',
        'sidebar_inspector_empty': 'Select a group or item from the left pane to edit it.',
        'sidebar_label_field': 'Label',
        'sidebar_icon_field': 'Icon',
        'sidebar_duplicate': 'Duplicate',
        'sidebar_group_label': 'Group',
        'sidebar_new_group': 'New Group',
        'sidebar_copy_suffix': 'Copy',
        'sidebar_no_home_items': 'Use the default titlebar Home button link.',
        'sidebar_home_use_default': 'Use the default titlebar Home button link',
        'sidebar_no_available': 'No available entries match the current selection.',
        'sidebar_no_selected': 'No entries selected yet.',
        'sidebar_show_system_items': 'Show system items',
        'sidebar_sections_manager_tooltip': 'Dynamic Sections Manager',

        # Options page
        'options_title': 'Application Options',
        'accessibility': 'Accessibility',
        'accessibility_desc': 'Customize the display to assist users with visual impairments or color blindness.',
        'high_contrast': 'High Contrast',
        'grayscale': 'Grayscale',
        'invert': 'Invert Colors',
        'large_text': 'Large Display (150%)',
        'no_animations': 'Reduce Animations',
        'system_info': 'System Info',
        'server_time': 'Server Time (Backend)',
        'memory': 'Memory',
        'storage': 'Storage',
        'os_info': 'Operating System (OS)',
        'python_version': 'Python Version',
        'django_version': 'Django Version',
        'decrypter_version': 'Decrypter Version',
        'drf_version': 'DRF Version',
        'api_status': 'API Status',
        'api_online': 'Online',
        'api_offline': 'Offline',
        'status_online': 'Online',
        'status_offline': 'Offline',
        'status_degraded': 'Degraded',
        'status_configured': 'Configured',
        'service_error_detail': 'Error: {error}',
        'service_db_version_lookup_failed': 'Connected, but version lookup failed: {error}',
        'service_cache_probe_unexpected': 'Cache responded, but the health probe returned an unexpected value.',
        'service_api_http_status': 'Endpoint responded with HTTP {status}.',
        'service_celery_missing_package': 'Celery-related settings were detected, but the celery package is not installed.',
        'service_celery_configured': 'Celery settings were detected. Worker health is not auto-checked here.',
        'database': 'Database',
        'cache': 'Cache',
        'tasks': 'Task Server',
        'microsys_version': 'microSYS Version',
        'themes': 'Color Theme',
        'themes_desc': 'Choose your preferred color theme for the interface.',
        'typography': 'Typography',
        'typography_desc': 'Choose your preferred font for the interface.',
        'table_density': 'Table Density',
        'table_density_desc': 'Control how much vertical space data tables use while you work.',
        'sidebar_density': 'Sidebar Density',
        'sidebar_density_desc': 'Control how much vertical space the sidebar navigation uses while you work.',
        'table_density_balanced': 'Balanced',
        'table_density_balanced_desc': 'Comfortable default for everyday admin work.',
        'table_density_dense': 'Dense',
        'table_density_dense_desc': 'Fits more rows on screen with tighter spacing.',
        'table_density_roomy': 'Roomy',
        'table_density_roomy_desc': 'Uses larger rows and more breathing room.',
        'sidebar_density_balanced_desc': 'The default balance between density and readability.',
        'sidebar_density_dense_desc': 'Tighter rows and spacing for a denser sidebar.',
        'sidebar_density_roomy_desc': 'Larger row height and spacing for a more relaxed sidebar.',
        'table_empty_title': 'No records found',
        'table_empty_desc': 'There is no matching data to display right now.',
        'table_rows_per_page': 'Rows',
        'table_total_records': 'Total records',
        'table_page_label': 'Page',
        'table_of_label': 'of',
        'theme_white': 'White',
        'theme_royal': 'Royal',
        'theme_gold': 'Gold',
        'theme_green': 'Green',
        'theme_red': 'Red',
        'theme_mono': 'Mono',
        'theme_dark': 'Dark',
        'theme_gothic': 'Gothic',
        'theme_retro': 'Retro',
        'autofill': 'Autofill',
        'autofill_desc': 'Auto-fill data from the last entered record (date, number, ...).',
        'on_off': 'On / Off',
        'reset_defaults': 'Reset Defaults',
        'reset_desc': 'Reset all user preferences to default (Theme, Language, etc).',
        'reset_btn': 'Reset Now',
        'reset_success': 'Preferences reset successfully.',
        'reset_confirm': 'Are you sure you want to reset all preferences? Page will reload.',
        'language': 'Language',
        'language_desc': 'Choose your preferred display language.',

        # Autofill toast
        'autofill_enabled': 'Autofill enabled.',
        'autofill_disabled': 'Autofill disabled.',

        # Auth / Admin verbose names (used by apps.py)
        'auth_system': 'Authentication System',
        'permission_manage': 'Permission Management',
        'permissions': 'Permissions',

        # Sidebar system group
        'sidebar_system': 'System Management',

        # Table headers (used by tables.py)
        'tbl_username': 'Username',
        'tbl_phone': 'Phone',
        'tbl_email': 'Email',
        'tbl_scope': 'Scope',
        'tbl_full_name': 'Full Name',
        'tbl_is_staff': 'Staff',
        'tbl_is_active': 'Active',
        'tbl_last_login': 'Last Login',
        'tbl_timestamp': 'Timestamp',
        'tbl_model_name': 'Model',
        'tbl_action': 'Action',
        'tbl_object_id': 'Object ID',
        'tbl_number': 'Target',
        "tbl_name": 'Name',
        'tbl_created_by': 'Created By',
        'tbl_created_at': 'Created At',
        'tbl_scope_default': 'General',

        # Filter placeholders
        'label_keyword': 'Search...',
        # 'filter_search': 'Search',
        'filter_year': 'Year',
        'filter_date': 'Date',
        'filter_date_from': 'From Date',
        'filter_date_to': 'To Date',
        'filter_scope': 'Scope',
        'filter_all': 'All',
        'filter_from': 'From ',
        'filter_to': 'To ',

        # Template strings (manage_users)
        'add_user': 'Add New User',
        'manage_scopes_btn': 'Manage Scopes',
        'enable_scopes': 'Enable Scopes',
        'confirm_delete': 'Confirm Delete',
        'delete_user_msg': 'Are you sure you want to delete user',
        'yes_delete': 'Yes, Delete',
        'cancel': 'Cancel',
        'confirm': 'Confirm',
        'loading': 'Loading...',
        'scope_warning_title': 'Important Warning',
        'scope_warning_msg': 'Are you sure you want to enable the scopes system?',
        'scope_warning_detail': 'Warning: After enabling and assigning users to scopes, you will not be able to disable it later without risking loss of user structure data, permissions, or access to existing application data.',
        'scope_warning_note': 'Only a Superuser can enable or disable this feature.',
        'yes_activate': 'Yes, Activate',
        'cannot_disable_scopes': 'Cannot disable — users are assigned to scopes',

        # Template strings (sections)
        'manage_label': 'Manage',
        'list_label': 'List of',
        'save': 'Save',
        'add_label': 'Add',
        'edit_label': 'Edit',
        'edit_user_label': 'Edit User',
        'edit_permissions_label': 'Edit Permissions',
        'delete_label': 'Delete',
        'subsections': 'Subsections',
        'subsection_help_tooltip': 'To edit or delete: right-click the subsection, or long-press it on mobile.',
        'subsection_empty': 'No subsections found',
        'subsection_locked_tooltip': 'This item cannot be deleted because it is linked to other records',
        'error_generic': 'An error occurred!',
        'no_models': 'No models available.',
        'model_load_error': 'Error loading model.',
        'view_label': 'View',
        'delete_error_related': 'Cannot delete record because it is linked to other items.',

        # Activity log page
        'log_title': 'Activity Log',
        'no_items': 'No items found',
        'select_all': 'Select All',
        'unit_items': 'items',

        # Apps & Models (Permissions / Sidebar)
        'app_microsys': 'System Management',
        'app_auth': 'Authentication System',
        'app_admin': 'Administration',
        'app_sessions': 'Sessions',
        'app_contenttypes': 'Content Types',
        'model_user': 'Users',
        'model_group': 'Groups',
        'model_permission': 'Permissions',
        'model_scope': 'Scopes',
        'model_log': 'Activity Logs',
        'model_scope_settings': 'Scope Settings',
        'model_systemsettings': 'System Settings',
        'model_system_settings': 'System Settings',
        'model_section': 'Sections',
        'model_subsection': 'Subsections',
        'model_profile': 'User Profile',
        'model_useractivitylog': 'Activity Log',
        'model_password': 'Password',
        'model_user profile': 'User Data',
        'model_auth': 'Authentication',

        # Theme picker
        'theme_pick_color': 'Pick Color',
        'theme_change': 'Change Theme',
        'sidebar_density_runtime': 'Sidebar Density',
        'theme_light': 'Light',
        'theme_blue': 'Royal',
        'theme_gold': 'Gold',
        'theme_green': 'Green',
        'theme_red': 'Red',
        'theme_mono': 'Mono',
        'theme_dark': 'Dark',
        'theme_gothic': 'Gothic',
        'theme_retro': 'Retro',
        'theme_neon': 'Neon',
        'sidebar_reorder': 'Reorder',

        # User form Labels
        'user_label': 'User',
        'reset_password': 'Reset Password',
        'form_username': 'Username',
        'form_password': 'Password',
        'form_password_confirm': 'Confirm Password',
        'form_firstname': 'First Name',
        'form_lastname': 'Last Name',
        'form_email': 'Email Address',
        'form_phone': 'Phone Number',
        'form_scope': 'Scope',
        'form_permissions': 'Permissions',
        'form_is_staff': 'Enable Staff Access',
        'form_is_active': 'Active Account',
        'form_profile_pic': 'Profile Picture',
        'form_new_password': 'New Password',
        'form_confirm_new_password': 'Confirm New Password',
        'form_old_password': 'Current Password',
        'form_scope_name': 'Scope Name',
        
        # User form Help Text
        'help_username': 'Username must be unique, 20 characters or fewer. Letters, digits and @/./+/-/_ only.',
        'help_email': 'Enter a valid email address (optional).',
        'help_phone': 'Enter a valid phone number (optional).',
        'help_password_common': """
        <ul class="mb-0 ps-3"><li>Password must be at least 8 characters long.</li>
        <li>Password can’t be too similar to your other personal information.</li>
        <li>Password can’t be a commonly used password or entirely numeric.</li></ul>
        """,
        'help_password_match': 'Enter the same password again, for verification.',
        'help_is_active': 'Designates whether this user should be treated as active. Unselect this instead of deleting accounts.',
        'help_is_staff': 'Enables staff access. The final tier depends on scope and selected permissions.',
        'help_is_staff_no_perm': 'You do not have permission to assign this user as staff.',
        'help_scope_self': 'You cannot change your own scope to prevent removing yourself from admin privileges.',
        
        # Buttons
        'btn_add': 'Add',
        'enable': 'Enable',
        'btn_update': 'Update',
        'btn_cancel': 'Cancel',
        'btn_next': 'Next',
        'btn_prev': 'Previous',
        'btn_change_password': 'Change Password',
        
        # Permissions UI
        'can_add': 'Can add',
        'can_change': 'Can change',
        'can_delete': 'Can delete',
        'can_view': 'Can view',
        'permission_word': 'permission',
        'perm_staff_access': 'Staff Tier & Access',
        'perm_manage_users': 'User Management',
        'perm_view_sections': 'View Sections',
        'perm_manage_sections': 'Sections Management',
        'perm_manage_scopes': 'Global Staff Access',
        'help_perm_manage_scopes': 'Creates Global Staff access only when the user has no assigned scope.',
        'perm_manage_staff': 'Can Assign Staff Roles',
        'help_perm_manage_staff': 'Lets this staff user assign staff access to other users. It does not widen their own scope.',
        'perm_view_activity_log': 'View activity log',
        'perm_view_activitylog': 'View activity log',
        'staff_tier_preview': 'Staff Tier Preview',
        'staff_tier_preview_caption': 'Read-only summary based on staff access, scope, and selected permissions.',
        'tier_regular_user': 'Standard User',
        'tier_desc_regular_user': 'No staff user-management access is enabled for this account.',
        'tier_superuser': 'Superuser',
        'tier_desc_superuser': 'Full system administration access without scope or permission limits.',
        'tier_global_staff': 'Global Staff',
        'tier_desc_global_staff': 'Staff access across all scopes, including scope management.',
        'tier_central_staff': 'Central Staff',
        'tier_desc_central_staff': 'Staff access limited to scopeless users in the core system.',
        'tier_scoped_staff': 'Scoped Staff',
        'tier_desc_scoped_staff': 'Staff access is limited to the assigned scope.',
        'tier_delegate_badge': 'Can Assign Staff Roles',
        'tier_warning_needs_staff': 'Staff-related permissions are selected, but staff access is not enabled yet.',
        'tier_warning_scoped_manage_scopes': 'Global Staff access is ineffective while a scope is assigned.',
        'tier_cap_regular_1': 'No staff access to the user directory.',
        'tier_cap_regular_2': 'Can use normal account features only.',
        'tier_cap_regular_3': 'Staff-related permissions stay inactive until staff access is enabled.',
        'tier_cap_superuser_1': 'Can view and manage all users and scopes.',
        'tier_cap_superuser_2': 'Can assign any staff tier or permission.',
        'tier_cap_superuser_3': 'Can access full system administration features.',
        'tier_cap_global_1': 'Can view and manage users across all scopes.',
        'tier_cap_global_2': 'Can create and manage scopes.',
        'tier_cap_global_3': 'Can assign users to any scope or leave them scopeless.',
        'tier_cap_central_1': 'Can manage scopeless users only.',
        'tier_cap_central_2': 'Cannot view scoped users or their data.',
        'tier_cap_central_3': 'Cannot assign scopes or manage scopes.',
        'tier_cap_scoped_1': 'Can manage users inside the assigned scope only.',
        'tier_cap_scoped_2': 'Cannot access users outside the assigned scope.',
        'tier_cap_scoped_3': 'Scope assignment controls visibility and user-management actions.',

        # Activity Log Actions
        'action_login': 'Login',
        'action_logout': 'Logout',
        'action_create': 'Create',
        'action_update': 'Update',
        'action_delete': 'Delete',
        'action_view': 'View',
        'action_download': 'Download',
        'action_confirm': 'Confirm',
        'action_reject': 'Reject',
        'action_reset': 'Reset',

        # Activity Log Modal
        'view_details': 'View Details',
        'activity_details': 'Activity Details',
        'label_related_object': 'Related Object',
        'label_changes': 'Changes / Details',
        'label_previous_value': 'Previous Value',
        'label_new_value': 'New Value',
        'label_value': 'Value',
        'label_file': 'File',
        'label_count': 'Count',
        'label_download': 'Download',
        'label_items': 'items',
        'log_change_set': 'Set',
        'log_change_cleared': 'Cleared',
        'log_change_changed': 'Changed',
        'log_change_info': 'Info',
        'log_value_empty': 'Empty',
        'no_details': 'No specific details recorded.',
        'btn_close': 'Close',

        # Profile
        'role_superuser': 'Superuser',
        'role_staff': 'Staff User',
        'role_user': 'Standard User',
        'btn_update_data': 'Update Info',
        'btn_home': 'Home',
        'btn_confirm_password_change': 'Confirm Password Change',
        'profile_update_title': 'Update Profile',
        'save_changes': 'Save Changes',
        'profile_picture': 'Profile Picture',
        'signed_in_devices': 'Signed-in Devices',
        'signed_in_devices_desc': 'Review active browser sessions and sign out of devices you no longer use.',
        'active_sessions': 'active',
        'current_session': 'Current Session',
        'trusted_device_badge': 'Trusted Device',
        'trusted_until': 'Trusted Until',
        'session_expires': 'Expires',
        'current': 'Current',
        'no_active_sessions': 'No active sessions were found.',
        
        # Messages
        'msg_password_changed': 'Password changed successfully!',
        'msg_form_error': 'There was an error with the submitted data',

        # User Detail View
        'user_details_title': 'User Details',
        'user_details_header': 'User Detail',
        'account_active': 'Active',
        'account_inactive': 'Inactive',
        'account_active_tooltip': 'Account is active',
        'account_inactive_tooltip': 'Account is inactive',
        'staff_permissions_tooltip': 'Has administrative permissions',
        'role_type': 'Role Type',
        'date_joined': 'Date Joined',
        'back_to_users': 'Back to User Management',
        'tbl_staff_tier': 'Staff Tier',

        # Profile Enhancements
        'stats_total_actions': 'Total Actions',
        'stats_docs_created': 'Additions',
        'stats_recent_activity': 'Recent Activity',
        'stats_system_interactions': 'System Interactions',
        'profile_completeness': 'Profile Completeness',
        'account_health': 'Account Health',
        'account_health_good': 'Good',
        'account_health_attention': 'Needs Attention',
        'badge_verified': 'Verified',
        'badge_admin': 'Admin',
        'badge_staff': 'Staff',
        'timeline_empty': 'No recent activity',

        # 2FA
        '2fa_title': 'Two-Factor Authentication',
        '2fa_desc': 'Secure your account with a verification code sent to your email.',
        '2fa_enable': 'Enable 2FA',
        '2fa_disable': 'Disable 2FA',
        '2fa_enabled_msg': 'Two-Factor Authentication enabled successfully.',
        '2fa_disabled_msg': 'Two-Factor Authentication disabled.',
        '2fa_verify_title': 'Verify Your Identity',
        '2fa_verify_desc': 'We sent a verification code to your email. Please enter it below.',
        'totp_scan_instruction': 'Scan this QR code with your authenticator app (e.g., Google Authenticator or Authy).',
        'otp_sent_instruction': 'Enter the code sent to your',
        '2fa_code': 'Verification Code',
        '2fa_verify_btn': 'Verify',
        '2fa_resend_btn': 'Resend Code',
        '2fa_code_sent': 'A new code has been sent to your email.',
        '2fa_invalid_code': 'Invalid or expired code.',
        '2fa_setup_email_subject': '2FA Activation Code - microsys',
        '2fa_login_email_subject': 'Login Code - microsys',
        '2fa_email_body': 'Your verification code is: {code}. Valid for 5 minutes.',
        '2fa_method_backup': 'Backup Codes',
        'backup_codes_title': 'Backup Codes',
        'backup_codes_desc': 'Use these codes to access your account if you lose your device. Each code can be used once.',
        'btn_view_generate': 'View / Generate',
        'btn_download_txt': 'Download as TXT',
        'btn_close': 'Close',
        '2fa_backup_instruction': 'Enter one of your 8-digit backup codes.',
        '2fa_enabled_success': 'Two-Factor Authentication Enabled!',
        'backup_codes_warning': '<strong>Warning:</strong> These recovery codes will only be shown <strong>once</strong>. Save them immediately.',
        'btn_close_reload': 'I have saved my codes',
        '2fa_method_email': 'Email Authentication',
        '2fa_method_phone': 'Phone Authentication',
        '2fa_method_totp': 'Authenticator App',
        '2fa_confirm_email_title': 'Confirm Email 2FA',
        '2fa_confirm_email_instruction': 'Confirm or update the email address before we send a setup code.',
        '2fa_confirm_email_label': 'Email address for 2FA',
        '2fa_confirm_email_help': 'Confirm this is the email address that should receive your 2FA setup code.',
        '2fa_confirm_email_send': 'Send setup code',
        'btn_edit': 'Edit',
        'btn_reset': 'Reset',
        'modal_confirm_title': 'Are you sure?',
        'modal_confirm_msg': 'Proceed with this action?',
        'msg_confirm_generate_backup': 'Generating new backup codes will invalidate any existing codes. Are you sure you want to proceed?',
        'msg_confirm_disable_2fa': 'Are you sure you want to disable 2FA for this method?',
        'msg_confirm_sign_out_session': 'Are you sure you want to sign out this device session?',
        'current_password_prompt': 'Please enter your current password to continue.',
        'current_password_required': 'Please enter your current password.',
        'current_password_incorrect': 'Current password is incorrect.',
        'status_enabled': 'Enabled',
        'btn_generate_new': 'Generate New Codes',
        'duration_minute': 'minute',
        'duration_minutes': 'minutes',
        'duration_hour': 'hour',
        'duration_hours': 'hours',
        'duration_day': 'day',
        'duration_days': 'days',
        'duration_week': 'week',
        'duration_weeks': 'weeks',
        'duration_month': 'month',
        'duration_months': 'months',
        'duration_and': ',',
        'no_activity_recorded': 'No activity recorded yet.',

        # Tutorial / Guided Tour
        'tut_btn_next': 'Next',
        'tut_btn_prev': 'Previous',
        'tut_btn_skip': 'Skip',
        'tut_btn_finish': 'Finish',
        'tut_of': 'of',
        
        # Dashboard Tutorial
        'tut_sidebar_title': 'Sidebar Navigation',
        'tut_sidebar_desc': 'You can navigate between different system sections from here at any time.',
        'tut_titlebar_title': 'Titlebar',
        'tut_titlebar_desc': 'Contains the system name and your personal user menu.',
        'tut_usermenu_title': 'User Menu',
        'tut_usermenu_desc': 'From here you can log out or go to your profile page.',
        'tut_maincontent_title': 'Workspace',
        'tut_maincontent_desc': 'This is where tables, forms, and the main system content appear.',
        
        # Lists / Tables Tutorial
        'tut_search_title': 'Quick Search',
        'tut_search_desc': 'Search for records using titles, keywords, or numbers.',
        'tut_add_title': 'Add New',
        'tut_add_desc': 'Click here to add a new record or item to this section.',
        'tut_table_title': 'Data Table',
        'tut_table_desc': 'Records are displayed here. You can click on items to view or edit them.',
        
        # Sections Tutorial
        'tut_sections_list_title': 'Sections List',
        'tut_sections_list_desc': 'This list displays all departments and entities defined in the system.',
        
        # Users Tutorial
        'tut_users_roles_title': 'User Roles',
        'tut_users_roles_desc': 'You can distinguish permission roles through badges (Admin, Staff, User).',
        'tut_users_row_title': 'User Details & Actions',
        'tut_users_row_desc': 'Double-click any row to open the user details card, including their activity logs.',
        'tut_users_add_btn_title': 'Add New User',
        'tut_users_add_btn_desc': 'Click here to create a new user account and configure their permissions.',
        'tut_users_scopes_title': 'Scope Management',
        'tut_users_scopes_desc': 'Scopes restrict users from viewing certain data unless they belong to the authorized department.',
        
        # Logs Tutorial
        'tut_logs_row_title': 'Activity Details',
        'tut_logs_row_desc': 'Double-click any row or click the details button to see exactly what changed.',
        
        # Profile Tutorial
        'tut_profile_stats_title': 'Profile Statistics',
        'tut_profile_stats_desc': 'Find quick statistics about your activity within the system here.',
        'tut_profile_details_title': 'Personal Information',
        'tut_profile_details_desc': 'Your account details, including email, phone number, and system role are displayed here.',
        'tut_profile_edit_title': 'Update Info',
        'tut_profile_edit_desc': 'Use this button to edit your profile data or change your avatar.',
        'tut_profile_2fa_title': 'Security Settings (2FA)',
        'tut_profile_2fa_desc': 'You can enable and disable two-factor authentication methods to secure your account.',
        'tut_profile_activity_title': 'Recent Activity',
        'tut_profile_activity_desc': 'Track your system interactions and recently performed actions here.',
        
        # Options Tutorial
        'tut_options_tabs_title': 'Settings Tabs',
        'tut_options_tabs_desc': 'Browse the tabs to access accessibility, theme, and autofill options.',
        'tut_options_access_title': 'Accessibility',
        'tut_options_access_desc': 'This section lets you customize the reading experience with high contrast or by disabling animations.',
        'tut_options_info_title': 'System Info',
        'tut_options_info_desc': 'View details regarding the server environment, storage, and underlying service versions.',
        'tut_options_theme_title': 'Themes & Colors',
        'tut_options_theme_desc': 'Choose the theme that suits you, changes apply immediately.',
        'tut_options_lang_title': 'Language Settings',
        'tut_options_lang_desc': 'You can switch between available interface languages here.',
        'tut_options_autofill_title': 'Smart Autofill',
        'tut_options_autofill_desc': 'When enabled, the system remembers previous inputs to expedite form filling.',

        # Registration
        'register_title': 'Register',
        'create_account': 'Create an account',
        'btn_register': 'Register',
        'back_to_login': 'Back to login',
        'check_email': 'Check your email',
        'registration_sent_desc': 'If the address can be registered, a verification link has been sent.',
        'account_verified': 'Account verified',
        'account_active_signed_in': 'Your account is active and you are signed in.',
        'btn_continue': 'Continue',
        'email_verified': 'Email verified',
        'account_pending_approval': 'Your account is waiting for approval.',
        'verification_expired': 'Verification expired',
        'verification_link_expired': 'The verification link is no longer valid.',
        'register_again': 'Register again',
        'verification_failed': 'Verification failed',
        'verification_link_invalid': 'The verification link is invalid or has already been used.',
        'btn_register_again': 'Register',

        # Pending Registrations
        'pending_registrations': 'Pending registrations',
        'tbl_email_header': 'Email',
        'tbl_name_header': 'Name',
        'tbl_created_header': 'Created',
        'actions': 'Actions',
        'btn_approve': 'Approve',
        'btn_reject': 'Reject',
        'no_pending_registrations': 'No pending registrations.',

        # 2FA Verify page extras
        '2fa_totp_or_email_instruction': 'Enter your authenticator code. You can request an email code if enabled.',
        '2fa_email_request_instruction': 'Request an email code, then enter it here.',
        '2fa_send_email_code': 'Send email code',
        '2fa_use_backup_code': 'Use backup code',
        '2fa_email_sent_instruction': 'Email code sent. Enter the 6-digit code here.',
        '2fa_send_email_instead': 'Use Email Instead',
        '2fa_use_authenticator': 'Use Authenticator App',
        '2fa_return_to_email': 'Return to Email Code',
        '2fa_return_to_authenticator': 'Return to Authenticator App',
        '2fa_return_to_default': 'Return to Default Method',
        '2fa_email_resend_wait': 'Resend available in {seconds}s.',
        '2fa_trust_device_label': 'Trust this device for 30 days',
        '2fa_invalid_email': 'Enter a valid email address.',
        '2fa_totp_prepare_failed': 'Unable to prepare authenticator setup. Check server dependencies and try again.',
        '2fa_totp_generate_failed': 'Unable to generate authenticator setup. Try again.',

        # Dynamic Modal
        'manage_records': 'Manage Records',
        'close_label': 'Close',

        # Activity Log / Detail Modal
        'error_loading_details': 'Error loading details.',
        'label_id': 'ID',

        # Options page extras
        'email_label': 'Email',

        # View Messages (errors & success)
        'err_no_edit_permission_account': 'You do not have permission to edit this account!',
        'err_no_edit_permission_user': 'You do not have permission to edit this user!',
        'err_cannot_edit_global_staff': 'Central Staff cannot edit Global Staff users.',
        'err_cannot_delete_self': 'You cannot delete your own account!',
        'err_cannot_delete_superuser': 'You do not have permission to delete superusers!',
        'err_cannot_delete_last_superuser': 'Cannot delete the last system superuser!',
        'err_no_delete_permission_user': 'You do not have permission to delete this user!',
        'err_no_edit_permission_user_reset': 'You do not have permission to edit this user!',
        'msg_registration_not_configured': 'Registration email delivery is not configured.',
        'msg_verification_email_failed': 'We could not send the verification email. Please try again later.',
        'msg_registration_approved': 'Registration approved.',
        'msg_registration_rejected': 'Registration rejected.',
        'err_invalid_method': 'Invalid method.',
        'err_already_enabled': 'Already enabled.',
        'err_failed_send_otp': 'Failed to send OTP.',
        'msg_code_sent': 'Code sent.',
        'err_unable_send_code': 'Unable to send code.',
        'err_not_authenticated': 'Not authenticated.',
        'err_totp_unavailable': 'TOTP is unavailable.',
        'err_unable_save_totp': 'Unable to save authenticator setup. Run database migrations and try again.',
        'device_unknown': 'Unknown device',
        'device_browser_generic': 'Browser',
        'device_platform_generic': 'device',
        'device_label_pattern': '{browser} on {platform}',
        'err_subsection_id_missing': 'Subsection identifier is missing.',
        'err_subsection_not_found': 'Subsection not found.',
        'msg_subsection_added': 'Added',
        'err_subsection_add_failed': 'Error adding',
        'msg_subsection_edited': 'Updated',
        'err_subsection_edit_failed': 'Error updating',
        'err_cannot_delete_related': 'Cannot delete this item because it is linked to other records.',
        'msg_subsection_deleted': 'Deleted',
        'err_unable_update_preferences': 'Unable to update preferences.',
        'err_invalid_method_api': 'Invalid method.',
        'help_is_staff_no_perm_form': "You don't have permission to assign this user as staff.",
    },
}


from django.apps import apps
from django.conf import settings
from importlib import import_module
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def _discover_and_merge_translations():
    """
    Auto-discover translations from all installed apps.
    Looks for 'translations.py' in each app and 'MS_TRANSLATIONS' dict.
    Returns a merged dictionary of all translations.
    """
    # Keep source ownership intact for the translation matrix while merging app keys.
    merged_strings = {
        lang: dict(strings) if isinstance(strings, dict) else strings
        for lang, strings in MICROSYS_STRINGS.items()
    }

    for app_config in apps.get_app_configs():
        # Skip microsys itself as we already loaded it
        if app_config.name == 'microsys':
            continue
            
        try:
            # Try to import translations module
            module = import_module(f"{app_config.name}.translations")
            
            # Look for MS_TRANSLATIONS
            app_strings = getattr(module, 'MS_TRANSLATIONS', None)
            
            if app_strings and isinstance(app_strings, dict):
                # Deep merge logic
                for lang, keys in app_strings.items():
                    if lang not in merged_strings:
                        merged_strings[lang] = {}
                    merged_strings[lang].update(keys)
                    
        except ImportError:
            # App has no translations.py, just skip
            continue
        except Exception as e:
            logger.warning(f"Error loading translations from {app_config.name}: {e}")
            continue
            
    return merged_strings


@lru_cache(maxsize=1)
def _discover_translation_source_layers():
    """
    Return source-aware translation layers for matrix grouping.
    The merged runtime catalog still uses _discover_and_merge_translations().
    """
    sources = [
        {
            'id': 'microsys',
            'label': 'Microsys',
            'type': 'core',
            'translations': MICROSYS_STRINGS,
        }
    ]

    for app_config in apps.get_app_configs():
        if app_config.name == 'microsys':
            continue

        try:
            module = import_module(f"{app_config.name}.translations")
            app_strings = getattr(module, 'MS_TRANSLATIONS', None)
        except ImportError:
            continue
        except Exception as e:
            logger.warning(f"Error loading translations from {app_config.name}: {e}")
            continue

        if not isinstance(app_strings, dict) or not app_strings:
            continue

        sources.append({
            'id': str(app_config.label or app_config.name).replace('.', '_'),
            'label': str(getattr(app_config, 'verbose_name', '') or app_config.label or app_config.name),
            'type': 'app',
            'translations': app_strings,
        })

    return sources


def _translation_layer_keys(layer):
    keys = set()
    if not isinstance(layer, dict):
        return keys
    for values in layer.values():
        if isinstance(values, dict):
            keys.update(str(key) for key in values.keys())
    return keys


def discover_translation_languages(*extra_layers):
    """Return language codes that have translation strings, without enabling them."""
    languages = set()
    for layer in (_discover_and_merge_translations(), *extra_layers):
        if not isinstance(layer, dict):
            continue
        for code, values in layer.items():
            if isinstance(values, dict) and values:
                languages.add(str(code).split('-')[0].lower())
    return sorted(languages)


def _build_translation_matrix_row(key, enabled_codes, base_strings, project_strings, overrides):
    values = {}
    base_values = {}
    override_values = {}
    sources = {}
    for lang in enabled_codes:
        core_value = MICROSYS_STRINGS.get(lang, {}).get(key)
        discovered_value = base_strings.get(lang, {}).get(key)
        project_value = project_strings.get(lang, {}).get(key) if isinstance(project_strings.get(lang), dict) else None
        override_value = overrides.get(lang, {}).get(key) if isinstance(overrides.get(lang), dict) else None

        base_value = project_value if project_value is not None else discovered_value
        value = override_value if override_value is not None else base_value
        values[lang] = '' if value is None else str(value)
        base_values[lang] = '' if base_value is None else str(base_value)
        override_values[lang] = '' if override_value is None else str(override_value)
        if override_value is not None:
            sources[lang] = 'override'
        elif project_value is not None:
            sources[lang] = 'project'
        elif core_value is not None:
            sources[lang] = 'core'
        elif discovered_value is not None:
            sources[lang] = 'app'
        else:
            sources[lang] = 'missing'

    cells = [
        {
            'language': lang,
            'value': values.get(lang, ''),
            'base_value': base_values.get(lang, ''),
            'override_value': override_values.get(lang, ''),
            'source': sources.get(lang, 'missing'),
        }
        for lang in enabled_codes
    ]
    return {
        'key': key,
        'values': values,
        'base_values': base_values,
        'override_values': override_values,
        'sources': sources,
        'cells': cells,
    }


def _enabled_language_codes(enabled_languages):
    return [
        str(code).split('-')[0].lower()
        for code in (enabled_languages or {})
        if str(code or '').strip()
    ]


def build_translation_matrix_groups(enabled_languages, overrides=None):
    """
    Build grouped editor data. Groups are used as UI tabs: Microsys, each app,
    project settings translations, and override-only keys.
    """
    enabled_codes = _enabled_language_codes(enabled_languages)
    base_strings = _discover_and_merge_translations()
    project_config = getattr(settings, 'MICROSYS_CONFIG', {})
    project_strings = project_config.get('translations', {}) if isinstance(project_config, dict) else {}
    overrides = overrides if isinstance(overrides, dict) else {}

    groups = []
    claimed_keys = set()
    for source in _discover_translation_source_layers():
        source_keys = sorted(_translation_layer_keys(source.get('translations')))
        rows = []
        for key in source_keys:
            if key in claimed_keys:
                continue
            claimed_keys.add(key)
            rows.append(_build_translation_matrix_row(key, enabled_codes, base_strings, project_strings, overrides))
        if rows:
            groups.append({
                'id': source['id'],
                'label': source['label'],
                'type': source['type'],
                'rows': rows,
            })

    project_keys = sorted(_translation_layer_keys(project_strings) - claimed_keys)
    if project_keys:
        groups.append({
            'id': 'project',
            'label': 'Project translations',
            'type': 'project',
            'rows': [
                _build_translation_matrix_row(key, enabled_codes, base_strings, project_strings, overrides)
                for key in project_keys
            ],
        })
        claimed_keys.update(project_keys)

    override_only_keys = sorted(_translation_layer_keys(overrides) - claimed_keys)
    if override_only_keys:
        groups.append({
            'id': 'runtime',
            'label': 'Settings overrides',
            'type': 'override',
            'rows': [
                _build_translation_matrix_row(key, enabled_codes, base_strings, project_strings, overrides)
                for key in override_only_keys
            ],
        })

    return groups


def build_translation_matrix(enabled_languages, overrides=None):
    """
    Build editor data for enabled languages.
    Existing code/app/project values prefill cells; overrides remain the only saved layer.
    """
    rows = []
    for group in build_translation_matrix_groups(enabled_languages, overrides):
        rows.extend(group.get('rows', []))
    return rows

def get_current_language_code(request=None):
    from django.utils.translation import get_language
    
    # ── 1. Fetch System Settings ──
    try:
        from microsys.utils import get_system_config
        sys_config = get_system_config()
        default_sys_lang = sys_config.get('default_language', 'en')
        allow_user_language_override = bool(sys_config.get('allow_user_language_override', True))
        available_languages = sys_config.get('languages', {}) or {}
    except Exception:
        default_sys_lang = 'en'
        allow_user_language_override = True
        available_languages = {}
        
    lang_code = None
    
    # ── 2. Resolve Language Code ──
    if not request:
        try:
            from microsys.middleware import get_current_request
            request = get_current_request()
        except Exception:
            pass

    if request:
        preview_lang = None
        if hasattr(request, 'session'):
            preview_lang = request.session.get('lang')
            if request.session.get('ms_force_language_preview') and preview_lang:
                lang_code = preview_lang

        # 2.A User Profile Preference
        if not lang_code and allow_user_language_override and hasattr(request, 'user') and getattr(request.user, 'is_authenticated', False):
            profile = getattr(request.user, 'profile', None)
            if profile:
                user_prefs = getattr(profile, 'preferences', None) or {}
                lang_code = user_prefs.get('language')
        
        # 2.B Session
        if not lang_code and allow_user_language_override and hasattr(request, 'session'):
            lang_code = request.session.get('lang') or request.session.get('django_language')
    
    # 2.C System Default Language
    if not lang_code:
        lang_code = default_sys_lang
    
    # 2.D Django Thread Local
    if not lang_code:
        lang_code = get_language()
        
    lang = lang_code or default_sys_lang
    if available_languages and lang.split('-')[0] not in available_languages:
        lang = default_sys_lang
    # handle en-us -> en
    return lang.split('-')[0]


def get_strings(lang_code=None, overrides=None):
    """
    Get the translation dict for a given language code.
    If lang_code is not provided, dynamically resolves it using get_current_language_code().
    Merges project-level overrides on top of the base strings automatically.
    """
    try:
        from microsys.utils import get_system_config
        sys_config = get_system_config()
        default_sys_lang = sys_config.get('default_language', 'en')
        if overrides is None:
            overrides = sys_config.get('translations', {})
    except Exception:
        default_sys_lang = 'en'
        overrides = overrides or {}
        
    lang = lang_code
    if not lang:
        lang = get_current_language_code()
    else:
        lang = lang.split('-')[0]
    
    # ── 3. Merge Strings ──
    all_strings = _discover_and_merge_translations()
    base = dict(all_strings.get(default_sys_lang, {}))

    if lang != default_sys_lang:
        lang_strings = all_strings.get(lang, {})
        base.update(lang_strings)

    if overrides and isinstance(overrides, dict):
        lang_overrides = overrides.get(lang, {})
        base.update(lang_overrides)

    return base

def lazy_translator(key, default_val):
    """
    Returns a lazy proxy that evaluates to the translated string
    at render time, using the current thread's language.
    Perfect for patching global class attributes like Column.verbose_name.
    """
    from django.utils.functional import lazy
    def _translate():
        s = get_strings()
        return s.get(key, default_val)
    # Using str type so Django templates format it correctly
    return lazy(_translate, str)()
