function showTab(button) {
	// Apply styling to selected button
	document.querySelectorAll('.tab-selector > button').forEach(
		b => b.dataset.selected = b === button ? 'true' : 'false'
	);

	// Show desired tab and hide all others
	document.querySelectorAll('#home > div:not(.tab-selector)').forEach(
		e => e.classList.add('hidden')
	);
	document.getElementById(button.dataset.target).classList.remove('hidden');
};

// 
// Filling library
// 
function fillTable(table, results) {
	table.querySelectorAll('button.entry:not(.add-entry)').forEach(e => e.remove());

	results.forEach(r => {
		const entry = document.createElement('button');
		entry.classList.add('entry');
		entry.dataset.id = r.id;
		entry.addEventListener('click', e => showEdit(r.id, table));
		if (r.color !== null)
			entry.style.setProperty('--color', r.color);
		
		const title = document.createElement('h2');
		title.innerText = r.title;
		entry.appendChild(title);

		if (table === types.reminder) {
			const time = document.createElement('p');
			var offset = new Date(r.time * 1000).getTimezoneOffset() * -60;
			var d = new Date((r.time + offset) * 1000);
			var formatted_date = d.toLocaleString('en-CA').slice(0,10) + ' ' + d.toTimeString().slice(0,5);
			if (r.repeat_interval !== null) {
				if (r.repeat_interval === 1) {
					var quantity = r.repeat_quantity.endsWith('s') ? r.repeat_quantity.slice(0, -1) : r.repeat_quantity;
					var interval_text = ` (each ${quantity})`;
				} else {
					var quantity = r.repeat_quantity.endsWith('s') ? r.repeat_quantity : r.repeat_quantity + 's';
					var interval_text = ` (every ${r.repeat_interval} ${quantity})`;
				};
				formatted_date += interval_text;
			};
			time.innerText = formatted_date;
			entry.appendChild(time);
		};
		
		table.appendChild(entry);
		
		if (title.clientHeight < title.scrollHeight)
			entry.classList.add('expand');
	});
	table.querySelectorAll('button.entry:not(.add-entry)').forEach(r => r.classList.add('fit'));
};

function fillLibrary(url, type) {
	fetch(url)
	.then(response => {
		if (!response.ok) return Promise.reject(response.status);
		return response.json();
	})
	.then(json => fillTable(type, json.result))
	.catch(e => {
		if (e === 401)
			window.location.href = `${url_prefix}/`;
		else
			console.log(e);
	});
};

function fillReminders() {
	fillLibrary(`/api/reminders?api_key=${api_key}`, types.reminder);
};

function fillStaticReminders() {
	fillLibrary(`/api/staticreminders?api_key=${api_key}`, types.static_reminder);
}

function fillTemplates() {
	fillLibrary(`/api/templates?api_key=${api_key}`, types.template);
};

// 
// Library search
// 
function searchLibrary() {
	const query = document.querySelector('#search-input').value;
	fetch(`${url_prefix}/api/reminders/search?api_key=${api_key}&query=${query}`)
	.then(response => {
		if (!response.ok) return Promise.reject(response.status);
		return response.json();
	})
	.then(json => fillTable(types.reminder, json.result))
	.catch(e => {
		if (e === 401)
			window.location.href = `${url_prefix}/`;
		else
			console.log(e);
	});
};

function clearSearchLibrary() {
	document.querySelector('#search-input').value = '';
	fillReminders();
};

// code run on load

document.querySelectorAll('.tab-selector > button').forEach(b => {
	b.addEventListener('click', e => showTab(b));
});

fillReminders();
fillStaticReminders();
fillTemplates();
setInterval(fillReminders, 60000);

document.querySelector('#search-form').setAttribute('action', 'javascript:searchLibrary();');
document.querySelector('#clear-button').addEventListener('click', e => clearSearchLibrary());
