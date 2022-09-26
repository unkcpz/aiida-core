# -*- coding: utf-8 -*-
###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida-core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""Test run on containrized code."""
from aiida import orm
from aiida.engine import run_get_node
from aiida.plugins import CalculationFactory

def test_add_singularity():
    ArithmeticAddCalculation = CalculationFactory('core.arithmetic.add')

    inputs = {
        'code': orm.load_code('add-singularity@localhost'),
        'x': orm.Int(4),
        'y': orm.Int(6),
        'metadata': {
            'options': {
                'resources': {
                    'num_machines': 1,
                    'num_mpiprocs_per_machine': 1
                }
            }
        }
    }

    res, node = run_get_node(ArithmeticAddCalculation, **inputs)
    assert 'sum' in res
    assert 'remote_folder' in res
    assert 'retrieved' in res
    assert res['sum'].value == 10
    
def test_multiple_numpy_singularity_installed():
    TemplatereplacerCalculation = CalculationFactory('core.templatereplacer')
    inputs = {
        'code': orm.load_code('numpy-mul-installed@localhost'),
        'metadata': {
            'options': {
                'resources': {
                    'num_machines': 1,
                    'tot_num_mpiprocs': 1
                }
            }
        },
        'template':
        orm.Dict(
            dict={
                'input_file_template': "import numpy as np; res = np.multiply({x}, {y}); print(res)",
                'input_file_name': 'doubler.py',
                'cmdline_params': ['doubler.py'],
                'output_file_name': 'output.txt',
            }
        ),
        'parameters':
        orm.Dict(dict={
            'x': 2,
            'y': 4,
        }),
    }
    res, node = run_get_node(TemplatereplacerCalculation, **inputs)
    assert 'output_parameters' in res
    assert 'remote_folder' in res
    assert 'retrieved' in res
    assert res['output_parameters']['value'] == 8
    
def test_doubler_numpy_singularity_portable():
    TemplatereplacerCalculation = CalculationFactory('core.templatereplacer')
    inputs = {
        'code': orm.load_code('numpy-double-portable'),
        'metadata': {
            'computer': orm.load_computer('localhost'), # any computer has singularity installed
            'options': {
                'resources': {
                    'num_machines': 1,
                    'tot_num_mpiprocs': 1
                }
            }
        },
        'template':
        orm.Dict(
            dict={
                'input_file_template': "{x}",
                'input_file_name': 'input.txt',
                'cmdline_params': ['input.txt'],
                'output_file_name': 'output.txt',
            }
        ),
        'parameters':
        orm.Dict(dict={
            'x': 4,
        }),
    }
    res, node = run_get_node(TemplatereplacerCalculation, **inputs)
    assert 'output_parameters' in res
    assert 'remote_folder' in res
    assert 'retrieved' in res
    assert res['output_parameters']['value'] == 8
    
def main():
    # test_add_singularity()
    # test_doubler_numpy_singularity_installed()
    test_doubler_numpy_singularity_portable()

if __name__ == '__main__':
    main()
