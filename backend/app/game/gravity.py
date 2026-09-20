from .models import Board, GravityDirection


def apply_gravity(
    board: Board,
    direction: GravityDirection,
) -> Board:
    """
    Apply gravity to the board.
    Pieces fall in the specified direction while preserving their relative order.
    Returns a NEW board without modifying the original.
    """

    rows = len(board)
    columns = len(board[0])

    new_board: Board = [
        [None for _ in range(columns)]
        for _ in range(rows)
    ]

    # Horizontal Gravity
    if direction in (GravityDirection.LEFT, GravityDirection.RIGHT):
        for row in range(rows):
            pieces = [
                piece 
                for piece in board[row] 
                if piece is not None
            ]

            empty_spaces = columns - len(pieces)

            if direction == GravityDirection.LEFT:
                new_board[row] = (
                    pieces + [None] * empty_spaces
                )

            else:
                new_board[row] = (
                [None] * empty_spaces + pieces
            )
    
    # Vertical Gravity
    elif direction in (GravityDirection.UP, GravityDirection.DOWN):
        for column in range(columns):
            pieces = [
                board[row][column]
                for row in range(rows)
                if board[row][column] is not None
            ]

            if direction == GravityDirection.UP:
                start_row = 0
            else:
                start_row = rows - len(pieces)
            
            for index, piece in enumerate(pieces):
                new_board[start_row + index][column] = piece
    
    else:
        raise ValueError(f'Invalid gravity direction: {direction}')
    
    return new_board
