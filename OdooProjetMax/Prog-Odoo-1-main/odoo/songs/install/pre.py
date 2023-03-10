# Copyright 2020 Kal-It
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import os
from base64 import b64encode

import anthem

MAIN_LANG = "fr_FR"
OPT_LANG = ""
ALL_LANG = [MAIN_LANG] + (OPT_LANG.split(';') if OPT_LANG else [])


@anthem.log
def setup_company(ctx):
    """ Setup company """
    # load logo on company
    logo_path = os.path.join(
        ctx.options.odoo_data_path, 'images/company_main_logo.png'
    )
    with open(logo_path, 'rb') as logo_file:
        logo_content = logo_file.read()
    b64_logo = b64encode(logo_content)

    values = {
        'name': "IUT",
        'street': "",
        'zip': "",
        'city': "",
        'country_id': ctx.env.ref('base.fr').id,
        'phone': "+33 00 00 00 00",
        'email': "",
        'website': "",
        'vat': "VAT",
        'logo': b64_logo,
        'currency_id': ctx.env.ref('base.EUR').id,
    }
    ctx.env.ref('base.main_company').write(values)


@anthem.log
def setup_language(ctx):
    """ Installing language and configuring locale formatting """
    for code in ALL_LANG:
        
        ctx.env['base.language.install'].create({'lang': code}).lang_install()
        
    # TODO check your date format
    ctx.env['res.lang'].search([]).write(
        {'grouping': [3, 0], 'date_format': '%d/%m/%Y'}
    )


@anthem.log
def set_default_partner_language(ctx):
    """Define default partner language"""
    Default = ctx.env['ir.default']
    Default.set('res.partner', 'lang', MAIN_LANG, condition=False)


@anthem.log
def main(ctx):
    """ Main: creating base config """
    setup_company(ctx)
    setup_language(ctx)
    set_default_partner_language(ctx)
