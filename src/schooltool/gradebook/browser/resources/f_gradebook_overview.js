/* This is the Javascript to be included when rendering the gradebook overview. */
function setNotEdited()
{
    edited = false;
}

function checkChanges()
{
    if (!edited)
        return;
    saveFlag = window.confirm(warningText);
    if (saveFlag == true)
        {
        button = document.getElementsByName('UPDATE_SUBMIT')[0];
        button.click();
        }
    else
        return true;
}

function onLoadHandler()
{
    // highlight error values
    for (a = 0; a < numactivities; a++)
    {
        activity = activities[a];
        for (s = 0; s < numstudents; s++)
        {
            name = activity + '_' + students[s];
            value = document.getElementById(name).value;
            setBackgroundColor(name, activity, value, true);
        }
    }
}

function handleCellFocus(cell, activity)
{
    currentCell = cell;
    cell.select();
}

function spreadsheetBehaviour(e)
{
    var keynum;
    if(window.event) // IE
    {
        keynum = e.keyCode;
    }
    else if(e.which) // Netscape/Firefox/Opera
    {
        keynum = e.which;
    }

    var my_name = currentCell.id;
    var s, a, done;
    done = new Boolean(false);

    for (s = 0; s != numstudents; s++)
    {
        for (a = 0; a != numactivities; a++)
        {
            try_name = activities[a] + '_' + students[s]
            if (try_name == my_name)
            {
                done = true;
                break;
            }
        }
        if (done == true)
            break;
    }

    var i_stayed_put = new Boolean(true);
    if (keynum == 37) // left arrow
    {
        if (a != 0) { a--; i_stayed_put = false;}
    }
    if (keynum == 39) // right arrow
    {
        if (a != numactivities - 1) {a++; i_stayed_put = false;}
    }
    if (keynum == 38) // up arrow
    {
        if (s != 0) {s--; i_stayed_put = false;}
    }
    if ((keynum == 40) || (keynum == 13)) // down arrow or enter
    {
        if (s != numstudents - 1) {s++; i_stayed_put = false;}
    }

    if (i_stayed_put == true)
        return true;
    var newname = activities[a] + '_' + students[s];
    var el = document.getElementsByName(newname)[0]
    el.focus();
    return false;
}

function checkValid(e, name)
{
    var activity = name.split('_')[0];
    if(activity == "fd")
        activity = name.split('_')[1];
    if (e == null)
        return true;

    var keynum;
    if(window.event) // IE
	{ 
	    keynum = e.keyCode;
	}
    else if(e.which) // Netscape/Firefox/Opera
	{
	    keynum = e.which;
	}
    if (keynum < 48 || (keynum > 57 && keynum < 65) || (keynum > 90 && keynum < 97) || keynum > 122)
	{
	    return true;
	}

    edited = true;
    var element = document.getElementById(name);
    var elementCell = document.getElementById(name+'_cell');
    var value = element.value;

    return setBackgroundColor(name, activity, value, false);
}

function setBackgroundColor(name, activity, value, errors_only)
{
    changeBackgroundColor(name+'_cell', 'default_bg');

    if (value == '')
        return true;

    // handle validation of discrete score system
    var actScores = scores[activity];
    if (actScores[0] == 'd')
    {
        for(var index in actScores)
        {
            if (index > 0 && value == actScores[index])
            {
                if (!errors_only)
                    changeBackgroundColor(name+'_cell', 'changed_bg');
                return true;
            }
        }  
        changeBackgroundColor(name+'_cell', 'error_bg');
        return false;   
    }

    // handle validation of ranged score system
    else
    {
        var min = parseInt(actScores[1]);
        var max = parseInt(actScores[2]);
        var intValue = parseInt(value);
        var regex = /[0-9]+$/;
        if (!value.match(regex) || intValue < min)
        {
            changeBackgroundColor(name+'_cell', 'error_bg');
            return false;   
        }
        if (errors_only)
            return true;
        if (intValue > max)
        {
            changeBackgroundColor(name+'_cell', 'warning_bg');
            return true;
        }
    }

    changeBackgroundColor(name+'_cell', 'changed_bg');
    return true;    
}

function changeBackgroundColor(id, class)    {
    obj = document.getElementById(id);
    $(obj).removeClass('default_bg');
    $(obj).removeClass('changed_bg');
    $(obj).removeClass('warning_bg');
    $(obj).removeClass('error_bg');
    $(obj).addClass(class);
}