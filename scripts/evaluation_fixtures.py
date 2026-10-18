"""Synthetic teaching files; never copies real student or university documents."""

import io
import zipfile
from xml.sax.saxutils import escape


def pdf(pages):
    objects = [
        None,
        b"<< /Type /Catalog /Pages 2 0 R >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    refs = []
    for text in pages:
        page_id = len(objects)
        content_id = page_id + 1
        refs.append(page_id)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        escaped = (
            text.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("\n", ") Tj 0 -20 Td (")
        )
        stream = ("BT /F1 12 Tf 45 780 Td (" + escaped + ") Tj ET").encode("ascii")
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
    objects[2] = (
        "<< /Type /Pages /Count "
        + str(len(refs))
        + " /Kids ["
        + " ".join(f"{n} 0 R" for n in refs)
        + "] >>"
    ).encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects[1:], 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    start = len(out)
    out += f"xref\n0 {len(objects)}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF".encode()
    return bytes(out)


def docx(text):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            + "".join(
                "<w:p><w:r><w:t>" + escape(p) + "</w:t></w:r></w:p>"
                for p in text.split("\n")
            )
            + "</w:body></w:document>",
        )
    return out.getvalue()


def pptx(slides):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        # The slide identifiers intentionally differ from presentation order.
        names = list(reversed(range(1, len(slides) + 1)))
        z.writestr(
            "ppt/presentation.xml",
            '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst>'
            + "".join(
                f'<p:sldId id="{256+i}" r:id="r{i}"/>' for i in range(len(slides))
            )
            + "</p:sldIdLst></p:presentation>",
        )
        z.writestr(
            "ppt/_rels/presentation.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="r{i}" Target="slides/slide{n}.xml"/>'
                for i, n in enumerate(names)
            )
            + "</Relationships>",
        )
        for n, text in zip(names, slides):
            z.writestr(
                f"ppt/slides/slide{n}.xml",
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>'
                + escape(text)
                + "</a:t></a:r></a:p></p:sld>",
            )
    return out.getvalue()


PHYSICS_PAGES = [
    "PHYS101 - Example teaching handout\nA traveling wave transfers energy. The disturbance travels through the medium.\nParticles of the medium move locally rather than following the crest across the pond.",
    "Frequency and period\nFrequency counts complete cycles per second and is measured in hertz (Hz).\nPeriod is the time for one complete cycle, measured in seconds. T = 1 / f.",
    "Wave speed and wavelength\nWavelength is the distance between consecutive matching points, such as crests.\nFor a periodic traveling wave, speed = frequency times wavelength.\nAt constant speed, doubling frequency halves wavelength.",
]
