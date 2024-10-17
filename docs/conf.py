# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'FreiCtrl_laser'
copyright = '2024, Artur Schneider (Optophysiology, University Freiburg)'
author = 'Artur'
release = '1.0.0'

import os
import sys

sys.path.insert(0, os.path.abspath('..'))


# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ['myst_parser', 'sphinx.ext.autodoc', 'sphinx.ext.napoleon',
              'sphinx.ext.viewcode']

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

autodoc_mock_imports = ['arduino_barcodes', 'circuitpython_code']

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'nature'
html_theme_options = {
    "sidebarwidth": "25%"
}
html_static_path = ['_static']
