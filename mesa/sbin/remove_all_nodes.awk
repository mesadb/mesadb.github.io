# 
# Copyright Vertica, an HP Company 2012 
# All rights reserved 
# 
# Description: awk tool, remove all nodes

# Clear the flag
BEGIN {
    processing = 0;
}

# Entering the section, set the flag
/^\[Nodes/ {
    processing = 1;
}

# Modify the line, if the flag is set
/^node/{
    if (processing) {
        skip = 1;
    }
}

# Clear the section flag (as we're in a new section)
/^\[$/ {
    processing = 0;
}

# Output a line (that we didn't output above)
/.*/ {
    if (skip)
        skip = 0;
    else
        print $0;
}
