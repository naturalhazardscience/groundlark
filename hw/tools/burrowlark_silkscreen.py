"""Apply Burrowlark's authored identity artwork without changing its circuitry."""
from hardware_require import require as _require_hardware
import argparse
import pcbnew as p

from kicad_support import add_text, save_board
from project_paths import board_dir, load_layout
from silkscreen import add_logo


def apply(board, spec):
    artwork = spec['silkscreen']
    labels = {'Groundlark FIELD A2', 'Burrowlark DAQUSB-01',
              artwork['name'], artwork['model_revision']}
    for item in list(board.GetDrawings()):
        if isinstance(item, p.PCB_TEXT) and item.GetText() in labels:
            board.Remove(item)
    add_logo(board, center=tuple(50 + value for value in artwork['logo_xy']))
    for text, position, size in [(artwork['name'], artwork['name_xy'], 1.4),
                                 (artwork['model_revision'], artwork['details_xy'], .8)]:
        add_text(board, text, *(50 + value for value in position), size)
    title = board.GetTitleBlock()
    title.SetTitle('Burrowlark DAQUSB-01 / atopile prototype')
    title.SetRevision(artwork['revision'])
    board.SetTitleBlock(title)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    name = 'groundlark-field-head'
    path = board_dir(name) / (name + '.kicad_pcb')
    board = p.LoadBoard(str(path))
    # Independent geometric records also include net names, layers and locks.
    from replay_trenz import copper
    before = copper(board)
    apply(board, load_layout(name)[name])
    _require_hardware((copper(board) == before), lambda: ('Silkscreen must not change copper'))
    save_board(path, board)
    _require_hardware((copper(p.LoadBoard(str(path))) == before), lambda: ('burrowlark_silkscreen.py:39: hardware validation condition'))
    print('Applied Burrowlark identity artwork; copper unchanged')


if __name__ == '__main__':
    main()
