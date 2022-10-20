"""Visit module to add odoo checks
"""

import os
import re

import astroid
import polib
from collections import defaultdict
from lxml import etree
from pylint.checkers import utils

from .. import misc, settings

ODOO_MSGS = {
    # C->convention R->refactor W->warning E->error F->fatal

    # Visit odoo module with settings.BASE_OMODULE_ID
    'E%d03' % settings.BASE_OMODULE_ID: (
        'Test folder imported in module %s',
        'test-folder-imported',
        settings.DESC_DFLT
    ),
    'R%d80' % settings.BASE_OMODULE_ID: (
        'Consider merging classes inherited to "%s" from %s.',
        'consider-merging-classes-inherited',
        settings.DESC_DFLT
    ),
    'W%d50' % settings.BASE_OMODULE_ID: (
        'Same Odoo module absolute import. You should use '
        'relative import with "." '
        'instead of "openerp.addons.%s"',
        'odoo-addons-relative-import',
        settings.DESC_DFLT
    ),
    'W%d38' % settings.BASE_OMODULE_ID: (
        'pass into block except. '
        'If you really need to use the pass consider logging that exception',
        'except-pass',
        settings.DESC_DFLT
    ),
}


DFTL_README_TMPL_URL = 'https://github.com/OCA/maintainer-tools' + \
    '/blob/master/template/module/README.rst'
DFTL_README_FILES = ['README.rst', 'README.md', 'README.txt']
DFTL_MIN_PRIORITY = 99
# Files supported from manifest to convert
# Extracted from openerp/tools/convert.py:def convert_file
DFLT_EXTFILES_CONVERT = ['csv', 'sql', 'xml', 'yml']
DFLT_EXTFILES_TO_LINT = DFLT_EXTFILES_CONVERT + [
    'po', 'js', 'mako', 'rst', 'md', 'markdown']
DFLT_IMPORT_NAME_WHITELIST = [
    # self-odoo
    'odoo', 'openerp',
    # Known external packages of odoo
    'PIL', 'PyPDF2', 'anybox.testing.openerp', 'argparse', 'babel', 'chardet',
    'dateutil', 'decorator', 'docutils', 'faces', 'feedparser',
    'gdata', 'gevent', 'greenlet', 'jcconv', 'jinja2',
    'ldap', 'lxml', 'mako', 'markupsafe', 'mock', 'odf',
    'ofxparse', 'openid', 'passlib', 'pkg_resources',
    'psutil', 'psycogreen', 'psycopg2', 'pyPdf', 'pychart',
    'pydot', 'pyparsing', 'pytz', 'qrcode', 'reportlab',
    'requests', 'serial', 'simplejson', 'six', 'suds',
    'unittest2', 'urllib3', 'usb', 'vatnumber', 'vobject', 'werkzeug',
    'wsgiref', 'xlrd', 'xlsxwriter', 'xlwt', 'yaml',
    # OpenUpgrade migration
    'openupgradelib'
]
DFTL_JSLINTRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
    'examples', '.jslintrc'
)
DFLT_DEPRECATED_TREE_ATTRS = ['colors', 'fonts', 'string']
DFTL_MANIFEST_DATA_KEYS = ['data', 'demo', 'demo_xml', 'init_xml', 'test',
                           'update_xml']


class ModuleChecker(misc.WrapperModuleChecker):
    name = settings.CFG_SECTION
    msgs = ODOO_MSGS
    options = (
        ('readme_template_url', {
            'type': 'string',
            'metavar': '<string>',
            'default': DFTL_README_TMPL_URL,
            'help': 'URL of README.rst template file',
        }),
        ('extfiles_to_lint', {
            'type': 'csv',
            'metavar': '<comma separated values>',
            'default': DFLT_EXTFILES_TO_LINT,
            'help': 'List of extension files to check separated by a comma.'
        }),
        ('min-priority', {
            'type': 'int',
            'metavar': '<int>',
            'default': DFTL_MIN_PRIORITY,
            'help': 'Minimum priority number of a view with replace of fields.'
        }),
        ('extfiles_convert', {
            'type': 'csv',
            'metavar': '<comma separated values>',
            'default': DFLT_EXTFILES_CONVERT,
            'help': 'List of extension files supported to convert '
                    'from manifest separated by a comma.'
        }),
        ('import_name_whitelist', {
            'type': 'csv',
            'metavar': '<comma separated values>',
            'default': DFLT_IMPORT_NAME_WHITELIST,
            'help': 'List of known import dependencies of odoo,'
            ' separated by a comma.'
        }),
    )

    class_inherit_names = []

    @utils.check_messages('consider-merging-classes-inherited')
    def visit_assign(self, node):
        import pdb;pdb.set_trace()
        if not self.odoo_node:
            return
        if not self.linter.is_message_enabled(
                'consider-merging-classes-inherited', node.lineno):
            return
        node_left = node.targets[0]
        if not isinstance(node_left, astroid.node_classes.AssignName) or \
                node_left.name not in ('_inherit', '_name') or \
                not isinstance(node.value, astroid.node_classes.Const) or \
                not isinstance(node.parent, astroid.ClassDef):
            return
        if node_left.name == '_name':
            node.parent.odoo_attribute_name = node.value.value
            return
        _name = getattr(node.parent, 'odoo_attribute_name', None)
        _inherit = node.value.value
        if _name and _name != _inherit:
            # Skip _name='model.name' _inherit='other.model' because is valid
            return
        key = (self.odoo_node, _inherit)
        node.file = self.linter.current_file
        self.inh_dup.setdefault(key, []).append(node)

    def _build_whitelist_module_patterns(self):
        known_patterns = []
        for known_pattern in self.config.import_name_whitelist:
            pattern = known_pattern.replace('*', '.*').replace('?', '.?')
            known_patterns.append(re.compile('^' + pattern + '$'))
        return known_patterns

    def open(self):
        """Define variables to use cache"""
        self.inh_dup = {}
        patterns = self._build_whitelist_module_patterns()
        self._whitelist_module_patterns = patterns
        super(ModuleChecker, self).open()

    def close(self):
        """Final process get all cached values and add messages"""
        for (odoo_node, class_dup_name), nodes in self.inh_dup.items():
            if len(nodes) == 1:
                continue
            path_nodes = []
            for node in nodes[1:]:
                relpath = os.path.relpath(node.file,
                                          os.path.dirname(odoo_node.file))
                path_nodes.append("%s:%d" % (relpath, node.lineno))
            self.add_message('consider-merging-classes-inherited',
                             node=nodes[0],
                             args=(class_dup_name, ', '.join(path_nodes)))

    def _get_odoo_module_imported(self, node):
        odoo_module = []
        if self.manifest_file and hasattr(node.parent, 'file'):
            relpath = os.path.relpath(
                node.parent.file, os.path.dirname(self.manifest_file))
            if os.path.dirname(relpath) == 'tests':
                # import errors rules don't apply to the test files
                # since these files are loaded only when running tests
                # and in such a case your
                # module and their external dependencies are installed.
                return odoo_module
        if isinstance(node, astroid.ImportFrom) and \
                ('openerp.addons' in node.modname or
                 'odoo.addons' in node.modname):
            packages = node.modname.split('.')
            if len(packages) >= 3:
                # from openerp.addons.odoo_module import models
                odoo_module.append(packages[2])
            else:
                # from openerp.addons import odoo_module
                odoo_module.append(node.names[0][0])
        elif isinstance(node, astroid.Import):
            for name, _ in node.names:
                if 'openerp.addons' not in name and 'odoo.addons' not in name:
                    continue
                packages = name.split('.')
                if len(packages) >= 3:
                    # import openerp.addons.odoo_module
                    odoo_module.append(packages[2])
        return odoo_module

    def check_odoo_relative_import(self, node):
        if self.odoo_module_name in self._get_odoo_module_imported(node):
            self.add_message('odoo-addons-relative-import', node=node,
                             args=(self.odoo_module_name))

    def check_folder_test_imported(self, node):
        if (hasattr(node.parent, 'file')
                and os.path.basename(node.parent.file) == '__init__.py'):
            package_names = []
            if isinstance(node, astroid.ImportFrom):
                if node.modname:
                    # from .tests import test_file
                    package_names = node.modname.split('.')[:1]
                else:
                    # from . import tests
                    package_names = [name for name, alias in node.names]
            elif isinstance(node, astroid.Import):
                package_names = [name[0].split('.')[0] for name in node.names]
            if "tests" in package_names:
                self.add_message('test-folder-imported', node=node,
                                 args=(node.parent.name,))

    @staticmethod
    def _is_absolute_import(node, name):
        modnode = node.root()
        importedmodnode = ModuleChecker._get_imported_module(node, name)
        if importedmodnode and importedmodnode.file and \
                modnode is not importedmodnode and \
                importedmodnode.name != name:
            return True
        return False

    @staticmethod
    def _get_imported_module(importnode, modname):
        try:
            return importnode.do_import_module(modname)
        except:
            pass

    def _is_module_name_in_whitelist(self, module_name):
        # Try to find most specific placement instruction match (if any)
        # (from isort place_module() method)
        parts = module_name.split('.')
        module_names_to_check = [
            '.'.join(parts[:first_k])
            for first_k in range(len(parts), 0, -1)
        ]
        # Check if one of the module name is part of the whitelist.
        # For an module name such as 'anybox.testing.openerp', the
        # modules names to check will be:
        # ['anybox.testing.openerp', 'anybox.testing', 'anybox']
        # Only one of them has to be in the whitelist to be accepted.
        for module_name_to_check in module_names_to_check:
            for pattern in self._whitelist_module_patterns:
                if pattern.match(module_name_to_check):
                    return True
        return False

    @utils.check_messages('odoo-addons-relative-import',
                          'test-folder-imported')
    def visit_importfrom(self, node):
        self.check_odoo_relative_import(node)
        self.check_folder_test_imported(node)

    @utils.check_messages('odoo-addons-relative-import',
                          'test-folder-imported')
    def visit_import(self, node):
        self.check_odoo_relative_import(node)
        self.check_folder_test_imported(node)
        for name, _ in node.names:
            if isinstance(node.scope(), astroid.Module):
                self._check_imported_packages(node, name)

    @utils.check_messages('except-pass')
    def visit_tryexcept(self, node):
        """Visit block try except"""
        for handler in node.handlers:
            if (not handler.name and
                    len(handler.body) == 1 and
                    isinstance(handler.body[0], astroid.node_classes.Pass)):
                self.add_message('except-pass', node=handler)

    def _check_missing_readme(self):
        """Check if exists ./README.{rst,md,txt} file
        :return: If exists return True else False
        """
        self.msg_args = (self.config.readme_template_url,)
        for readme in DFTL_README_FILES:
            if os.path.isfile(os.path.join(self.module_path, readme)):
                return True
        return False
