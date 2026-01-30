# FreeCAD Worker Container for PDM-Web
# Based on amrit3701/freecad-cli with SheetMetal addon

FROM amrit3701/freecad-cli:latest

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Add SheetMetal addon to Python path so FreeCAD can import it
ENV PYTHONPATH="/root/.FreeCAD/Mod/sheetmetal:${PYTHONPATH}"

# Create working directories
RUN mkdir -p /data/input /data/output /scripts

# Copy SheetMetal addon to FreeCAD's Mod directory
# The addon provides unfold/flatten capabilities for sheet metal parts
COPY FreeCAD/Mod/sheetmetal /root/.FreeCAD/Mod/sheetmetal

# Copy processing scripts (FreeCAD tools baked in; worker scripts mounted at runtime)
COPY FreeCAD/Tools/*.py /scripts/

# Set working directory
WORKDIR /data

# Default command - keep container running for job execution
CMD ["tail", "-f", "/dev/null"]
