"""Compact session receipts: three details and an exercise illustration."""
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A5, landscape
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

ROOT = Path(__file__).resolve().parent
ARTWORK = ROOT / 'assets/exercise-illustrations.png'
EXERCISES = {
    'Dumbbell curl': ('Dumbbell curls', 0, 0),
    'Floor push-up': ('Floor push-ups', 1, 0),
    'Shoulder press': ('Shoulder presses', 0, 1),
    'Bent-over row': ('Bent-over rows', 1, 1),
}


def export_session(path, exercise, count, elapsed, completed_at, sets_completed=1, reps_per_set=None):
    name, column, row = EXERCISES.get(exercise, (exercise, 0, 0))
    minutes, seconds = divmod(int(elapsed), 60)
    pdf = canvas.Canvas(str(path), pagesize=landscape(A5), pageCompression=1)
    pdf.setTitle(f'{name} - {completed_at:%Y-%m-%d}')
    pdf.setAuthor('FORM Studio')
    width, height = landscape(A5)
    pdf.setFillColor(HexColor('#FAFAF7'))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setFillColor(HexColor('#FFFFFF'))
    pdf.setStrokeColor(HexColor('#E0E6DF'))
    pdf.setLineWidth(.8)
    pdf.roundRect(32, 38, width-64, height-76, 18, fill=1, stroke=1)
    pdf.setFillColor(HexColor('#28624F'))
    pdf.roundRect(62, 350, 34, 3, 1.5, fill=1, stroke=0)

    # Session totals, duration, and date, without extra report boilerplate.
    pdf.setFillColor(HexColor('#233B33'))
    pdf.setFont('Helvetica-Bold', 16)
    pdf.drawString(62, 320, f'{name} completed:')
    reps = reps_per_set if reps_per_set is not None else count // max(1, sets_completed)
    metrics = [('Reps per set', reps), ('Sets', sets_completed), ('Total reps', count)]
    largest = max(stringWidth(str(value), 'Helvetica-Bold', 48) for _, value in metrics)
    number_size = min(48, 48 * 82 / max(1, largest))
    for x, (label, value) in zip((62, 162, 262), metrics):
        pdf.setFont('Helvetica', 11)
        pdf.setFillColor(HexColor('#758178'))
        pdf.drawString(x, 286, label)
        pdf.setFont('Helvetica-Bold', number_size)
        pdf.setFillColor(HexColor('#28624F'))
        pdf.drawString(x-2, 239, str(value))
    pdf.setStrokeColor(HexColor('#E5EAE3'))
    pdf.line(62, 220, 345, 220)

    pdf.setFont('Helvetica', 12)
    pdf.setFillColor(HexColor('#758178'))
    pdf.drawString(62, 179, 'Time taken:')
    pdf.setFont('Helvetica-Bold', 28)
    pdf.setFillColor(HexColor('#233B33'))
    pdf.drawString(61, 141, f'{minutes:02d}:{seconds:02d}')
    pdf.setFont('Helvetica', 12)
    pdf.setFillColor(HexColor('#758178'))
    pdf.drawString(62, 84, completed_at.strftime('%B %d, %Y'))

    if ARTWORK.is_file():
        x, y, size = 374, 170, 156
        pdf.setFillColor(HexColor('#F0F4EB'))
        pdf.circle(x+size/2, y+size/2, size/2, fill=1, stroke=0)
        # Clip the appropriate sprite cell in the PDF, keeping the source PNG intact.
        pdf.saveState()
        clip = pdf.beginPath()
        clip.rect(x, y, size, size)
        pdf.clipPath(clip, stroke=0)
        # Center the flatter push-up figure without revealing a neighboring tile.
        offset = 28 if exercise == 'Floor push-up' else 0
        tile = pdf.beginPath()
        tile.rect(x, y+offset, size, size)
        pdf.clipPath(tile, stroke=0)
        pdf.drawImage(str(ARTWORK), x-column*size, y+offset-(1-row)*size,
                      width=2*size, height=2*size, mask='auto')
        pdf.restoreState()

    pdf.showPage()
    pdf.save()
